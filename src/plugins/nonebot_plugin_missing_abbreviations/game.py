"""一局“缩略”的流程：发题、免费提示、收答案、判题、超时与结算。"""

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Optional

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Button, UniMessage
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils import escape_markdown
from nonebot_plugin_larkutils.command import get_command_prefix

from .config import config
from .judge import judge_guess
from .lang import lang
from .store import format_answer_summary, format_question, format_question_markdown, get_question_store

if TYPE_CHECKING:
    from .types import GeneratedQuestion

# “提示”的关键词（与按钮发送的内容一致），免费解锁下一条提示
HINT_KEYWORD = "提示"
HINT_KEYWORDS = frozenset({HINT_KEYWORD, "查看提示"})
# “查看答案”的关键词（与按钮发送的内容一致），额外接受“结束游戏 / 结束本局”的同义说法
REVEAL_KEYWORD = "查看答案"
REVEAL_KEYWORDS = frozenset({REVEAL_KEYWORD, "结束游戏", "结束本局"})
# “规则说明”的关键词（与按钮发送的内容一致），不消耗作答次数、也不会结束本局
RULES_KEYWORD = "规则说明"

# 会话 ID -> 当前进行中的游戏
games: dict[str, "MissingAbbreviationsGame"] = {}


@dataclass(slots=True)
class PlayerAction:  # pylint: disable=too-few-public-methods
    """玩家消息进入游戏循环后的动作。"""

    user_id: str
    text: str
    event: Event


def format_reward(value: float) -> str:
    """奖励展示：整数去掉小数点，其他保留两位。"""
    return str(int(value)) if float(value).is_integer() else str(round(value, 2))


async def build_rules_message(
    bot: Bot,
    user_id: str,
    game: Optional["MissingAbbreviationsGame"] = None,
) -> UniMessage:
    """构建规则说明消息：QQ 官方使用带示例表格的 Markdown 与操作按钮，其他平台返回纯文本。"""
    attempts = config.missing_abbreviations_max_attempts
    reward = format_reward(config.missing_abbreviations_reward)
    if not isinstance(bot, QQBot):
        return UniMessage(await lang.text("game.rules", user_id, attempts, reward))
    prefix = get_command_prefix()
    markdown = await lang.text("game.rules_markdown", user_id, attempts, reward)
    message = UniMessage().style(markdown, "markdown")
    if game is not None and not game.finished:
        buttons: list[Button] = [
            Button(
                "input",
                await lang.text("button.guess", user_id),
                text=f"{prefix}missing-abbreviations ",
            ),
        ]
        if game.question is not None and game.hints_revealed < len(game.question.hint):
            buttons.append(
                Button(
                    "enter",
                    await lang.text("button.hint", user_id),
                    text=f"{prefix}missing-abbreviations {HINT_KEYWORD}",
                ),
            )
        buttons.append(
            Button(
                "enter",
                await lang.text("button.reveal", user_id),
                text=f"{prefix}missing-abbreviations {REVEAL_KEYWORD}",
            ),
        )
        return message.keyboard(*buttons, row=2)
    return message.keyboard(
        Button(
            "enter",
            await lang.text("button.start", user_id),
            text=f"{prefix}missing-abbreviations",
        ),
    )


async def send_rules(
    bot: Bot,
    event: Event,
    user_id: str,
    game: Optional["MissingAbbreviationsGame"] = None,
) -> None:
    """向当前会话发送规则说明；QQ 官方发送失败时回退纯文本。"""
    try:
        await (await build_rules_message(bot, user_id, game)).send(target=event, bot=bot)
    except Exception:
        logger.opt(exception=True).warning("缩略：发送规则说明消息失败，回退纯文本")
    else:
        return
    plain = await lang.text(
        "game.rules",
        user_id,
        config.missing_abbreviations_max_attempts,
        format_reward(config.missing_abbreviations_reward),
    )
    try:
        await UniMessage(plain).send(target=event, bot=bot)
    except Exception:
        logger.opt(exception=True).warning("缩略：发送纯文本规则说明失败")


class MissingAbbreviationsGame:  # pylint: disable=too-many-instance-attributes
    """一个会话内的一局「缩略」游戏。

    作答统一走 ``asyncio.Queue``，由 ``run`` 串行处理，避免多个答题指令同时到来时
    把次数扣乱；「提示」与「查看答案」直接由处理器调用方法即时响应。任何会话消息都会
    刷新 ``last_activity``：连续三分钟没有任何消息时自动公布答案并结束本局。
    """

    def __init__(self, session_id: str, owner: str, bot: Bot, event: Event) -> None:
        self.session_id = session_id
        self.owner = owner
        self.bot = bot
        # 最新事件：QQ 官方机器人的被动回复要回复到最新消息
        self.last_event = event
        self.qq_mode = isinstance(bot, QQBot)
        self.question: Optional["GeneratedQuestion"] = None
        self.hints_revealed: int = 0
        self.attempts_left = config.missing_abbreviations_max_attempts
        self.queue: asyncio.Queue[PlayerAction] = asyncio.Queue()
        self.last_activity = time.monotonic()
        self.finished = False
        self.task: Optional[asyncio.Task[None]] = None

    # ---------- 生命周期 ----------

    def start(self) -> None:
        games[self.session_id] = self
        self.task = asyncio.create_task(self.run())

    async def run(self) -> None:
        try:
            store = get_question_store()
            if await store.count() == 0:
                await self._send_lang("game.preparing")
            try:
                await store.ensure_ready()
            except Exception:
                logger.opt(exception=True).warning("缩略：生成题目失败")
                await self.send_result(await lang.text("game.generate_failed", self.owner))
                return
            self.question = await store.pop()
            if self.question is None:
                await self.send_result(await lang.text("game.generate_failed", self.owner))
                return
            # 从题目真正发出开始计算三分钟无消息计时（生成题目可能很慢）
            self.touch()
            await self.send_question()
            store.schedule_prefetch()
            while not self.finished:
                action = await self.wait_action()
                if action is None:
                    await self.reveal("timeout")
                    break
                await self.handle_guess(action)
                if self.finished:
                    break
                if self.attempts_left <= 0:
                    await self.reveal("attempts")
                    break
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.opt(exception=True).error("缩略：游戏运行异常")
            if not self.finished:
                await self.send_result(await lang.text("game.error", self.owner))
        finally:
            self.finished = True
            if games.get(self.session_id) is self:
                games.pop(self.session_id, None)

    async def wait_action(self) -> Optional[PlayerAction]:
        """等待下一条动作；超过三分钟没有任何会话消息时返回 None。"""
        while not self.finished:
            remaining = self.last_activity + config.missing_abbreviations_idle_timeout - time.monotonic()
            if remaining <= 0:
                return None
            try:
                return await asyncio.wait_for(self.queue.get(), remaining)
            except TimeoutError:
                # 等待期间可能被其他会话消息刷新过 last_activity，重新计算剩余时间
                if time.monotonic() - self.last_activity >= config.missing_abbreviations_idle_timeout:
                    return None
        return None

    # ---------- 输入 ----------

    def touch(self, event: Optional[Event] = None, bot: Optional[Bot] = None) -> None:
        """刷新活跃时间；顺带把被动回复目标与发送机器人更新为同适配器的最新事件。"""
        self.last_activity = time.monotonic()
        if bot is not None and isinstance(bot, QQBot) != self.qq_mode:
            return
        if event is not None:
            self.last_event = event
        if bot is not None:
            self.bot = bot

    def can_answer(self, user_id: str) -> bool:
        """QQ 官方机器人下本局所有会话成员都能作答；其他适配器只有发起者能作答。"""
        return self.qq_mode or user_id == self.owner

    def submit_guess(self, user_id: str, text: str, event: Event, bot: Optional[Bot] = None) -> None:
        self.touch(event, bot)
        self.queue.put_nowait(PlayerAction(user_id, text, event))

    # ---------- 出题 ----------

    async def build_question_message(self) -> Optional[UniMessage]:
        """构建 QQ 官方机器人的题目消息（Markdown + 操作按钮）。"""
        if self.question is None:
            return None
        prefix = get_command_prefix()
        buttons: list[Button] = [
            Button(
                "input",
                await lang.text("button.guess", self.owner),
                text=f"{prefix}missing-abbreviations ",
            ),
        ]
        if self.hints_revealed < len(self.question.hint):
            buttons.append(
                Button(
                    "enter",
                    await lang.text("button.hint", self.owner),
                    text=f"{prefix}missing-abbreviations {HINT_KEYWORD}",
                ),
            )
        buttons.extend(
            [
                Button(
                    "enter",
                    await lang.text("button.reveal", self.owner),
                    text=f"{prefix}missing-abbreviations {REVEAL_KEYWORD}",
                ),
                Button(
                    "enter",
                    await lang.text("button.rules", self.owner),
                    text=f"{prefix}missing-abbreviations {RULES_KEYWORD}",
                ),
            ],
        )
        return (
            UniMessage()
            .style(format_question_markdown(self.question, revealed_hints=self.hints_revealed), "markdown")
            .keyboard(*buttons, row=2)
        )

    async def send_question(self) -> None:
        if self.question is None:
            return
        if self.qq_mode:
            message = await self.build_question_message()
            if message is not None:
                try:
                    await message.send(target=self.last_event, bot=self.bot)
                except Exception:
                    logger.opt(exception=True).warning("缩略：发送 QQ Markdown 题目失败，退回纯文本")
                    await self.send_text(format_question(self.question, revealed_hints=self.hints_revealed))
            return
        markdown = format_question_markdown(self.question, revealed_hints=self.hints_revealed)
        plain = format_question(self.question, revealed_hints=self.hints_revealed)
        hint = await lang.text("game.hint", self.owner)
        try:
            image = await md_to_pic(markdown)
        except Exception:
            logger.opt(exception=True).warning("缩略：题目图片渲染失败，退回纯文本")
            await self.send_text(f"{plain}\n{hint}")
            return
        await (UniMessage().image(raw=image) + UniMessage().text(hint)).send(target=self.last_event, bot=self.bot)

    # ---------- 免费提示 ----------

    async def _format_revealed_hints(self, count: Optional[int] = None) -> str:
        """格式化前 ``count`` 条已解锁的提示文本。"""
        if self.question is None:
            return ""
        limit = self.hints_revealed if count is None else count
        lines: list[str] = []
        for idx, hint_text in enumerate(self.question.hint[:limit], start=1):
            if idx == 1:
                lines.append(await lang.text("game.hint_mask", self.owner, hint_text))
            else:
                lines.append(await lang.text("game.hint_extra", self.owner, idx, hint_text))
        return "\n".join(lines)

    async def _build_hint_message(self, text: str) -> UniMessage:
        """构建提示消息：QQ 官方附带作答 / 继续提示 / 查看答案按钮，其他适配器返回纯文本。"""
        if not self.qq_mode:
            return UniMessage(text)
        prefix = get_command_prefix()
        buttons: list[Button] = [
            Button(
                "input",
                await lang.text("button.guess", self.owner),
                text=f"{prefix}missing-abbreviations ",
            ),
        ]
        if self.question is not None and self.hints_revealed < len(self.question.hint):
            buttons.append(
                Button(
                    "enter",
                    await lang.text("button.next_hint", self.owner),
                    text=f"{prefix}missing-abbreviations {HINT_KEYWORD}",
                ),
            )
        buttons.append(
            Button(
                "enter",
                await lang.text("button.reveal", self.owner),
                text=f"{prefix}missing-abbreviations {REVEAL_KEYWORD}",
            ),
        )
        markdown_text = "\n\n".join(escape_markdown(line) for line in text.splitlines())
        return UniMessage().style(markdown_text, "markdown").keyboard(*buttons, row=2)

    async def send_hint_message(self, text: str) -> None:
        """发送提示消息；QQ 官方发送失败时回退纯文本。"""
        if self.qq_mode:
            try:
                await (await self._build_hint_message(text)).send(target=self.last_event, bot=self.bot)
            except Exception:
                logger.opt(exception=True).warning(f"缩略：向会话 {self.session_id} 发送提示消息失败，回退纯文本")
            else:
                return
        await self.send_text(text)

    async def unlock_hint(self) -> None:
        """免费解锁下一条提示：不扣除作答次数，也不减少猜中奖励。"""
        if self.finished:
            return
        if self.question is None:
            await self._send_lang("game.preparing_short")
            return
        if not self.question.hint:
            await self._send_lang("game.no_hints_configured")
            return
        if self.hints_revealed < len(self.question.hint):
            self.hints_revealed += 1
            revealed_count = self.hints_revealed
            hints_text = await self._format_revealed_hints(revealed_count)
            text = await lang.text("game.hint_unlocked", self.owner, hints_text)
            await self.send_hint_message(text)
            return
        hints_text = await self._format_revealed_hints(len(self.question.hint))
        text = await lang.text("game.all_hints_revealed", self.owner, hints_text)
        await self.send_hint_message(text)

    # ---------- 作答与结算 ----------

    async def handle_guess(self, action: PlayerAction) -> None:
        if self.question is None:
            return
        guess = action.text.strip()
        if not guess:
            return
        outcome = judge_guess(guess, self.question)
        if outcome == "correct":
            self.finished = True
            reward = await grant_reward(action.user_id)
            answers_display, origin_display = format_answer_summary(self.question)
            if reward > 0:
                text = await lang.text(
                    "game.correct",
                    self.owner,
                    answers_display,
                    origin_display,
                    format_reward(reward),
                )
            else:
                text = await lang.text(
                    "game.correct_no_reward",
                    self.owner,
                    answers_display,
                    origin_display,
                )
            await self.send_result(text)
            return
        if outcome == "full_word":
            remind_text = await lang.text("game.full_word_remind", self.owner, guess, self.attempts_left)
            await self.send_hint_message(remind_text)
            return
        self.attempts_left -= 1
        if self.attempts_left > 0:
            await self.send_text(await lang.text("game.wrong", self.owner, guess, self.attempts_left))

    async def reveal(self, reason: Literal["timeout", "attempts"]) -> None:
        """公布答案并结束本局（幂等）：由游戏循环在超时 / 次数用尽时调用。"""
        if self.finished:
            return
        self.finished = True
        if self.question is not None:
            answers_display, origin_display = format_answer_summary(self.question)
        else:
            answers_display, origin_display = "?", "?"
        key = {
            "timeout": "game.reveal_timeout",
            "attempts": "game.reveal_attempts",
        }[reason]
        await self.send_result(await lang.text(key, self.owner, answers_display, origin_display))

    async def reveal_now(self) -> None:
        """玩家按下「查看答案」时立即结算并取消后台等待任务。"""
        if self.finished:
            return
        self.stop()
        if self.question is None:
            await self.send_result(await lang.text("game.reveal_before_question", self.owner))
            return
        answers_display, origin_display = format_answer_summary(self.question)
        await self.send_result(
            await lang.text("game.reveal_manual", self.owner, answers_display, origin_display),
        )

    def stop(self) -> None:
        """结束本局：标记完成、从会话表移除并取消仍在等待的后台任务。"""
        self.finished = True
        if games.get(self.session_id) is self:
            games.pop(self.session_id, None)
        task = self.task
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()

    # ---------- 发送 ----------

    async def build_result_message(self, text: str) -> UniMessage:
        """构建结算消息：QQ 官方附带「再来一局」按钮，其它适配器退回纯文本。"""
        if not self.qq_mode:
            return UniMessage(text)
        markdown_text = "\n\n".join(escape_markdown(line) for line in text.splitlines())
        return (
            UniMessage()
            .style(markdown_text, "markdown")
            .keyboard(
                Button(
                    "enter",
                    await lang.text("button.again", self.owner),
                    text=f"{get_command_prefix()}missing-abbreviations",
                ),
            )
        )

    async def send_result(self, text: str) -> None:
        """发送结算 / 答案消息，并在末尾提供再来一局的入口。"""
        if self.qq_mode:
            try:
                await (await self.build_result_message(text)).send(target=self.last_event, bot=self.bot)
            except Exception:
                # 带键盘的 markdown 消息发送失败（例如被动回复窗口过期）时，
                # 至少把答案用纯文本发出去，避免按键看起来毫无回应。
                logger.opt(exception=True).warning(f"缩略：向会话 {self.session_id} 发送结算消息失败，回退纯文本")
            else:
                return
        await self.send_text(f"{text}\n{await lang.text('game.again_hint', self.owner)}")

    async def send_text(self, text: str) -> None:
        try:
            await UniMessage(text).send(target=self.last_event, bot=self.bot)
        except Exception:
            logger.opt(exception=True).warning(f"缩略：向会话 {self.session_id} 发送消息失败")

    async def _send_lang(self, key: str, *args: object) -> None:
        await self.send_text(await lang.text(key, self.owner, *args))


async def grant_reward(user_id: str) -> float:
    """向猜中的玩家发放 VimCoin 奖励。"""
    try:
        user = await get_user(user_id)
        await user.add_vimcoin(config.missing_abbreviations_reward)
    except Exception:
        logger.opt(exception=True).warning(f"缩略：向 {user_id} 发放 VimCoin 失败")
        return 0.0
    return config.missing_abbreviations_reward
