from nonebot import on_command
from nonebot.adapters import Message
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot_plugin_larklang.__main__ import LangHelper
from nonebot_plugin_larkutils import get_user_id, review_text

from .censor import BoothillMode, censor

boothill = on_command("boothill")
boothill_fury = on_command("boothill-fury")
lang = LangHelper()


async def _process_boothill(matcher: Matcher, user_id: str, text: str, mode: BoothillMode) -> None:
    output_text = censor(text, mode)
    if not (await review_text(output_text))["compliance"]:
        await lang.finish("review_failed", user_id, matcher=matcher)
    await lang.finish("result", user_id, output_text, matcher=matcher, reply_message=True)


@boothill.handle()
async def _(user_id: str = get_user_id(), content: Message = CommandArg()) -> None:
    text = content.extract_plain_text()
    if not text.strip():
        await lang.finish("empty", user_id, matcher=boothill)
    await _process_boothill(boothill, user_id, text.strip(), "standard")


@boothill_fury.handle()
async def _(user_id: str = get_user_id(), content: Message = CommandArg()) -> None:
    text = content.extract_plain_text()
    if not text.strip():
        await lang.finish("empty", user_id, matcher=boothill_fury)
    await _process_boothill(boothill_fury, user_id, text.strip(), "fury")
