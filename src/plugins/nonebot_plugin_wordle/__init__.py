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
require("nonebot_plugin_render")
require("nonebot_plugin_larkuser")

from nonebot_plugin_alconna import Alconna, on_alconna, Args, UniMessage
from nonebot_plugin_larkutils import LatestEvent, get_user_id
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils.group import get_group_id
from nonebot_plugin_render import render_template
from nonebot_plugin_larkuser.utils.matcher import patch_matcher
from datetime import datetime
import traceback
from nonebot.exception import FinishedException
from nonebot.adapters import Bot, Event
from nonebot.log import logger
from nonebot.rule import Rule
from nonebot_plugin_minigame_api import create_minigame_session
from . import dictionary
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
    return await dictionary.is_valid_word(event.get_plaintext())


class Wordle:

    def __init__(
        self, correct_answer: str, user_id: str, translate: str, group_id: str, bot: Bot, event: Event
    ) -> None:
        self.history = []
        self.group_id = group_id
        self.correct_answer = correct_answer
        self.translate = translate
        self.user_id = user_id
        self.start_time = datetime.now()
        # 连续猜测时始终回复用户最新消息，避免 QQ 官方被动回复次数超限
        self.tracker = LatestEvent(event, bot)
        logger.debug(correct_answer)

    def __exit__(self, *_args) -> None:
        playing_groups.remove(self.group_id)

    def __enter__(self) -> "Wordle":
        playing_groups.append(self.group_id)
        return self

    async def ask(self) -> None:
        image = await render_template(
            "wordle.html.jinja",
            await lang.text("title", self.user_id),
            self.user_id,
            templates={
                "correct_answer": self.correct_answer,
                "history": self.history,
                "len": len,
                "answer_length": len(self.correct_answer),
            },
        )
        waiter = Waiter3(UniMessage().image(raw=image), self.group_id, Rule(check_word), event=self.tracker.event)
        try:
            await waiter.wait(int(290 - (datetime.now() - self.start_time).total_seconds()), False)
        except TimeoutError:
            self.tracker.update(waiter.get_event())
            await self.fail()
        self.tracker.update(waiter.get_event())
        result = waiter.get()
        if result == self.correct_answer:
            await self.win(waiter.user_id)
        elif result == "q":
            await self.fail()
        elif result:
            self.history.append(list(result))

    async def fail(self) -> None:
        await self.tracker.send(
            await lang.text("fail", self.user_id, self.correct_answer, self.translate), at_sender=True
        )
        await matcher.finish()

    async def loop(self) -> None:
        while len(self.history) < 6:
            await self.ask()
        await self.fail()

    async def win(self, user_id: str) -> None:
        session = await create_minigame_session(user_id, "wordle")
        session.start_time = self.start_time
        t = await session.finish()
        await session.add_points(round((7 - len(self.history)) * 5000 / t))
        await self.tracker.send(
            await lang.text("success", user_id, self.correct_answer, self.translate), at_sender=True
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
