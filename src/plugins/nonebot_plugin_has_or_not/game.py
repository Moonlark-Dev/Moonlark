"""一局“有无有无”的流程：发题、收答案、判题、超时与结算。"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Literal, Optional

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Button, UniMessage
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils.command import get_command_prefix

from .config import config
from .judge import judge_guess
from .lang import lang
from .store import format_question, get_question_store
from .types import GeneratedQuestion

ActionKind = Literal["guess", "reveal"]

# 查看答案的关键词（与按钮发送的内容一致）
REVEAL_KEYWORD = "查看答案"

# 会话 ID -> 当前进行中的游戏
games: dict[str, "HasOrNotGame"] = {}


@dataclass(slots=True)
class PlayerAction:  # pylint: disable=too-few-public-methods
    """玩家消息进入游戏循环后的动作。"""

    kind: ActionKind
    user_id: str
    text: str
    event: Event


def format_reward(value: float) -> str:
    """奖励展示：整数去掉小数点，其他保留两位。"""
    return str(int(value)) if float(value).is_integer() else str(round(value, 2))


class HasOrNotGame:  # pylint: disable=too-many-instance-attributes
    """一个会话内的一局游戏。

    输入统一走 ``asyncio.Queue``，由 ``run`` 串行处理，避免多个答题指令同时
    到来时并发判题、把次数扣乱。任何会话消息都会刷新 ``last_activity``：
    三分钟没有任何消息时自动公开答案。
    """

    def __init__(self, session_id: str, owner: str, bot: Bot, event: Event) -> None:
        self.session_id = session_id
        self.owner = owner
        self.bot = bot
        # 最新事件：QQ 官方机器人的被动回复要回复到最新消息
        self.last_event = event
        self.qq_mode = isinstance(bot, QQBot)
        self.question: Optional[GeneratedQuestion] = None
        self.attempts_left = config.has_or_not_max_attempts
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
                await self.send_lang("game.preparing")
            try:
                await store.ensure_ready()
            except Exception:
                logger.opt(exception=True).warning("有无有无：生成题目失败")
                await self.send_lang("game.generate_failed")
                return
            self.question = await store.pop()
            if self.question is None:
                await self.send_lang("game.generate_failed")
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
                if action.kind == "reveal":
                    await self.reveal("manual")
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
            logger.opt(exception=True).error("有无有无：游戏运行异常")
            if not self.finished:
                await self.send_lang("game.error")
        finally:
            self.finished = True
            games.pop(self.session_id, None)

    async def wait_action(self) -> Optional[PlayerAction]:
        """等待下一条动作；超过三分钟没有任何会话消息时返回 None。"""
        while not self.finished:
            remaining = self.last_activity + config.has_or_not_idle_timeout - time.monotonic()
            if remaining <= 0:
                return None
            try:
                return await asyncio.wait_for(self.queue.get(), remaining)
            except TimeoutError:
                # 等待期间可能被其他会话消息刷新过 last_activity，重新计算剩余时间
                if time.monotonic() - self.last_activity >= config.has_or_not_idle_timeout:
                    return None
        return None

    # ---------- 输入 ----------

    def touch(self, event: Optional[Event] = None, bot: Optional[Bot] = None) -> None:
        """刷新活跃时间；顺带把被动回复目标与发送机器人更新为最新事件。"""
        self.last_activity = time.monotonic()
        if event is not None:
            self.last_event = event
        if bot is not None:
            self.bot = bot

    def can_answer(self, user_id: str) -> bool:
        """QQ 官方机器人下本局所有会话成员都能作答；其他适配器只有发起者能作答。"""
        return self.qq_mode or user_id == self.owner

    def submit_guess(self, user_id: str, text: str, event: Event, bot: Optional[Bot] = None) -> None:
        self.touch(event, bot)
        self.queue.put_nowait(PlayerAction("guess", user_id, text, event))

    def request_reveal(self, event: Event, bot: Optional[Bot] = None) -> None:
        self.touch(event, bot)
        self.queue.put_nowait(PlayerAction("reveal", self.owner, "", event))

    # ---------- 出题 ----------

    async def send_question(self) -> None:
        if self.question is None:
            return
        markdown = format_question(self.question)
        if self.qq_mode:
            prefix = get_command_prefix()
            message = (
                UniMessage()
                .style(markdown, "markdown")
                .keyboard(
                    Button(
                        "input",
                        await lang.text("button.guess", self.owner),
                        text=f"{prefix}has-or-not ",
                    ),
                    Button(
                        "enter",
                        await lang.text("button.reveal", self.owner),
                        text=f"{prefix}has-or-not {REVEAL_KEYWORD}",
                    ),
                    row=2,
                )
            )
            await message.send(target=self.last_event, bot=self.bot)
            return
        hint = await lang.text("game.hint", self.owner)
        try:
            image = await md_to_pic(markdown)
        except Exception:
            logger.opt(exception=True).warning("有无有无：题目图片渲染失败，退回纯文本")
            await self.send_text(f"{markdown}\n{hint}")
            return
        await (UniMessage().image(raw=image) + UniMessage().text(hint)).send(target=self.last_event, bot=self.bot)

    # ---------- 作答与结算 ----------

    async def handle_guess(self, action: PlayerAction) -> None:
        if self.question is None:
            return
        guess = action.text.strip()
        if not guess:
            return
        if await judge_guess(guess, self.question.answer, action.user_id):
            self.finished = True
            reward = await self.grant_reward(action.user_id)
            if reward > 0:
                text = await lang.text("game.correct", self.owner, self.question.answer, format_reward(reward))
            else:
                text = await lang.text("game.correct_no_reward", self.owner, self.question.answer)
            await self.send_text(text)
            return
        self.attempts_left -= 1
        if self.attempts_left > 0:
            await self.send_text(await lang.text("game.wrong", self.owner, guess, self.attempts_left))

    async def grant_reward(self, user_id: str) -> float:
        try:
            user = await get_user(user_id)
            await user.add_vimcoin(config.has_or_not_reward)
            return config.has_or_not_reward
        except Exception:
            logger.opt(exception=True).warning(f"有无有无：向 {user_id} 发放 VimCoin 失败")
            return 0.0

    async def reveal(self, reason: Literal["timeout", "manual", "attempts"]) -> None:
        if self.finished:
            return
        self.finished = True
        answer = self.question.answer if self.question is not None else "?"
        key = {
            "timeout": "game.reveal_timeout",
            "manual": "game.reveal_manual",
            "attempts": "game.reveal_attempts",
        }[reason]
        await self.send_text(await lang.text(key, self.owner, answer))

    # ---------- 发送 ----------

    async def send_text(self, text: str) -> None:
        try:
            await UniMessage(text).send(target=self.last_event, bot=self.bot)
        except Exception:
            logger.opt(exception=True).warning(f"有无有无：向会话 {self.session_id} 发送消息失败")

    async def send_lang(self, key: str, *args: object) -> None:
        await self.send_text(await lang.text(key, self.owner, *args))
