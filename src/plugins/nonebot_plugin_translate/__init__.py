from nonebot.plugin import PluginMetadata, require
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-translate",
    description="不仅是翻译器，还是生草机。",
    usage="/t or /raw",
    config=Config,
)
require("nonebot_plugin_larkutils")
require("nonebot_plugin_alconna")
require("nonebot_plugin_larklang")

from nonebot_plugin_larkutils import get_user_id, review_text
from nonebot_plugin_alconna import Alconna, Args, Option, on_alconna, MultiVar
from nonebot.matcher import Matcher
from . import network
from .lang import lang


@on_alconna(
    Alconna(
        "t",
        Args["text", MultiVar(str)],
        Option("-s|--source", Args["source_lang", str, "en"]),
        Option("-t|--target", Args["target_lang", str, "zh"]),
    )
).handle()
async def _(
    text: list[str], source_lang: str, target_lang: str, matcher: Matcher, user_id: str = get_user_id()
) -> None:
    string_text = " ".join(text)
    result = await network.translate(string_text, source_lang, target_lang, user_id)
    result_str = result.data
    if not (c := await review_text(result_str))["compliance"]:
        await lang.finish("review_unpassed", user_id, c["message"])
    await matcher.finish(result_str, reply_message=True)


@on_alconna(Alconna("raw", Args["text", str])).handle()
async def _(text: str, matcher: Matcher, user_id: str = get_user_id()) -> None:
    result_str = (
        await network.translate(
            " ".join([(await network.translate(char, "zh", "en", user_id)).data for char in " ".join(text)]),
            "en",
            "zh",
            user_id,
        )
    ).data
    if not (c := await review_text(result_str))["compliance"]:
        await lang.finish("review_unpassed", user_id, c["message"])
    await matcher.finish(result_str, reply_message=True)
