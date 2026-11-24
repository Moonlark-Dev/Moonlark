from nonebot import require
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-wordle",
    description="",
    usage="",
    config=None,
)
require("nonebot_plugin_minigame_api")
require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larkuser")
require("nonebot_plugin_render")

from collections.abc import Callable

from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot.exception import FinishedException
from nonebot.log import logger
from nonebot.rule import Rule
from nonebot_plugin_alconna import Alconna, Args, Button, UniMessage, on_alconna
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkuser.utils.matcher import patch_matcher
from nonebot_plugin_larkutils import LatestEvent, get_user_id
from nonebot_plugin_larkutils.command import get_command_prefix
from nonebot_plugin_larkutils.group import get_group_id
from nonebot_plugin_minigame_api import create_minigame_session
from nonebot_plugin_render import render_template

from datetime import datetime
import traceback

from . import dictionary
from .panel import MAX_ATTEMPTS, QUIT_KEYWORD, build_latex_row, normalize_guess
from .waiter import Waiter3

lang = LangHelper()


async def check_length(length: int, user_id: str = get_user_id()) -> None:
    if length and length < 3:
        await lang.finish("wrong_length", user_id)
    try:
        await dictionary.get_dictionary(length)
    except KeyError:
        await lang.finish("wrong_length", user_id)


matcher = on_alconna(Alconna("wordle", Args["length", int, 5]))
patch_matcher(matcher)
playing_groups = []


async def check_word(event: Event) -> bool:
    """判断消息是否是本局可接受的输入：合法单词或放弃关键字。"""
    guess = normalize_guess(event.get_plaintext())
    if not guess:
        return False
    if guess == QUIT_KEYWORD:
        return True
    try:
        return await dictionary.is_valid_word(guess)
    except KeyError:
        return False


class Wordle:

    def __init__(
        self, correct_answer: str, user_id: str, translate: str, group_id: str, bot: Bot, event: Event
    ) -> None:
        self.history: list[list[str]] = []
        self.group_id = group_id
        self.correct_answer = correct_answer
        self.translate = translate
        self.user_id = user_id
        self.start_time = datetime.now()
        self.bot = bot
        self.answer_length = len(correct_answer)
        # 连续猜测时始终回复用户最新消息，避免 QQ 官方被动回复次数超限
        self.tracker = LatestEvent(event, bot)
        logger.debug(correct_answer)

    def __exit__(self, *_args) -> None:
        playing_groups.remove(self.group_id)

    def __enter__(self) -> "Wordle":
        playing_groups.append(self.group_id)
        return self

    def build_board(self, builder: Callable[[str, str, int], str], extra_guess: str = "") -> list[str]:
        """生成 6 行棋盘：已作答的行、本回合的作答（可选）与未作答的占位行。

        :param builder: 行渲染函数（LaTeX 或纯文本），签名为 ``(letters, answer, length) -> str``
        :param extra_guess: 已提交但还没记入历史的一行（例如获胜的那次作答）
        """
        rows = [builder("".join(guess), self.correct_answer, self.answer_length) for guess in self.history]
        if extra_guess:
            rows.append(builder(extra_guess, self.correct_answer, self.answer_length))
        rows.extend(builder("", self.correct_answer, self.answer_length) for _ in range(MAX_ATTEMPTS - len(rows)))
        return rows

    def attempts_used(self) -> int:
        """本回合是第几次尝试（用于面板展示，最多显示到 6）。"""
        return min(len(self.history) + 1, MAX_ATTEMPTS)

    async def build_panel(self) -> UniMessage:
        """构建本回合的作答面板。

        QQ 官方机器人下使用 Markdown + LaTeX 色块展示作答情况，并附带「作答」「放弃」
        按钮；其他适配器保持原来的渲染图片行为。
        """
        if isinstance(self.bot, QQBot):
            content = "\n\n".join(
                [
                    await lang.text("panel.title_md", self.user_id, self.answer_length),
                    await lang.text("panel.attempts_md", self.user_id, self.attempts_used(), MAX_ATTEMPTS),
                    "\n\n".join(self.build_board(build_latex_row)),
                    await lang.text("panel.legend", self.user_id),
                    await lang.text("panel.hint", self.user_id),
                ]
            )
            return (
                UniMessage()
                .style(content, "markdown")
                .keyboard(
                    Button("input", await lang.text("button.guess", self.user_id), text=get_command_prefix()),
                    Button("enter", await lang.text("button.give_up", self.user_id), text=QUIT_KEYWORD),
                    row=2,
                )
            )
        image = await render_template(
            "wordle.html.jinja",
            await lang.text("title", self.user_id),
            self.user_id,
            templates={
                "correct_answer": self.correct_answer,
                "history": self.history,
                "len": len,
                "answer_length": self.answer_length,
            },
        )
        return UniMessage().image(raw=image)

    async def build_result(self, text: str, extra_guess: str = "") -> str | UniMessage:
        """构建结算消息。

        QQ 官方机器人附上完整的 LaTeX 棋盘与「再来一局」按钮，其他适配器保持纯文本。
        """
        if not isinstance(self.bot, QQBot):
            return text
        content = "\n\n".join(
            [
                await lang.text("panel.title_md", self.user_id, self.answer_length),
                "\n\n".join(self.build_board(build_latex_row, extra_guess)),
                text,
            ]
        )
        return (
            UniMessage()
            .style(content, "markdown")
            .keyboard(
                Button(
                    "enter",
                    await lang.text("button.again", self.user_id),
                    text=f"{get_command_prefix()}wordle {self.answer_length}",
                )
            )
        )

    async def send_result(self, text: str, extra_guess: str = "") -> None:
        message = await self.build_result(text, extra_guess)
        if isinstance(message, str):
            await self.tracker.send(message, at_sender=True)
        else:
            await self.tracker.send(message)

    async def ask(self) -> None:
        waiter = Waiter3(await self.build_panel(), self.group_id, Rule(check_word), event=self.tracker.event)
        try:
            await waiter.wait(int(290 - (datetime.now() - self.start_time).total_seconds()), False)
        except TimeoutError:
            self.tracker.update(waiter.get_event())
            await self.fail()
        self.tracker.update(waiter.get_event())
        result = normalize_guess(waiter.get())
        if result == self.correct_answer:
            await self.win(waiter.user_id, result)
        elif result == QUIT_KEYWORD:
            await self.fail()
        elif result:
            self.history.append(list(result))

    async def fail(self) -> None:
        await self.send_result(await lang.text("fail", self.user_id, self.correct_answer, self.translate))
        await matcher.finish()

    async def loop(self) -> None:
        while len(self.history) < MAX_ATTEMPTS:
            await self.ask()
        await self.fail()

    async def win(self, user_id: str, guess: str) -> None:
        session = await create_minigame_session(user_id, "wordle")
        session.start_time = self.start_time
        t = await session.finish()
        await session.add_points(round((7 - len(self.history)) * 5000 / t))
        await self.send_result(
            await lang.text("success", user_id, self.correct_answer, self.translate), extra_guess=guess
        )
        await matcher.finish()


@matcher.handle()
async def _(bot: Bot, event: Event, length: int, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    if group_id in playing_groups:
        await lang.finish("playing", user_id)
    await check_length(length)
    correct_answer, translate = await dictionary.get_word_randomly(length)
    with Wordle(correct_answer, user_id, translate, group_id, bot, event) as wordle:
        try:
            await wordle.loop()
        except FinishedException:
            raise
        except Exception:
            logger.error(traceback.format_exc())
            await lang.finish("error", user_id, correct_answer, translate)
