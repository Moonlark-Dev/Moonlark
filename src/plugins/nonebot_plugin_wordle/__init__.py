from datetime import datetime
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
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils.group import get_group_id
from nonebot_plugin_render import render_template
from nonebot.adapters import Event
from nonebot.rule import Rule
from nonebot_plugin_minigame_api import create_minigame_session
from . import dictionary
from .waiter import Waiter3

lang = LangHelper()


async def check_length(length: int, user_id: str = get_user_id()) -> bool:
    if length < 3:
        await lang.send("wrong_length", user_id)
        return False
    try:
        await dictionary.get_dictionary(length)
    except KeyError:
        await lang.send("wrong_length", user_id)
        return False
    return True
        

matcher = on_alconna(Alconna("wordle", Args["length", int, 5]), rule=check_length)

async def check_word(event: Event) -> bool:
    return await dictionary.is_valid_word(event.get_plaintext())


@matcher.handle()
async def _(length: int, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    history = []
    correct_answer, translate = await dictionary.get_word_randomly(length)
    start_time = datetime.now()
    while len(history) < 6:
        image = await render_template(
            "wordle.html.jinja",
            await lang.text("title", user_id),
            user_id,
            templates={
                "correct_answer": correct_answer,
                "history": history
            }
        )
        waiter = Waiter3(UniMessage().image(raw=image), group_id, Rule(check_word))
        await waiter.wait()
        result = waiter.get()
        if result == correct_answer:
            user_id = waiter.user_id
            session = await create_minigame_session(user_id)
            session.start_time = start_time
            t = await session.finish()
            await session.add_points(round((7 - len(history)) * 5000 / t))
            await lang.finish("success", user_id, correct_answer, translate)
        history.append(list(result))
    await lang.finish("fail", user_id, correct_answer, translate)

        




