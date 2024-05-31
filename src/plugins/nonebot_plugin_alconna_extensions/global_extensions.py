from typing import Any, Dict

from arclet.alconna.exceptions import ArgumentMissing, ParamsUnmatched
from nonebot import require
from nonebot.adapters import Bot, Event, Message
from nonebot_plugin_alconna import Arparma, Extension, UniMessage
from nonebot_plugin_alconna.uniseg import reply_fetch

require("nonebot_plugin_larklang")
from ..nonebot_plugin_larklang import LangHelper

lang = LangHelper()


class UnmatchedExtension(Extension):
    @property
    def priority(self) -> int:
        return 14

    @property
    def id(self) -> str:
        return "lark_unmatched"

    async def parse_wrapper(self, bot: Bot, state: Dict[Any, Any], event: Event, res: Arparma) -> None:
        if res.matched:
            return
        err = res.error_info
        if isinstance(err, ArgumentMissing):
            argv = str(err)[3:-3]
            error_info = await lang.text("unmatched.missing", event.get_user_id(), argv)
        elif isinstance(err, ParamsUnmatched):
            argv = str(err)[3:-5]
            error_info = await lang.text("unmatched.unmatched", event.get_user_id(), argv)
        else:
            error_info = str(err)
        await UniMessage(error_info).send(event, bot, reply_to=True)
