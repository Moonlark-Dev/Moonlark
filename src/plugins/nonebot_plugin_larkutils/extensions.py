from nonebot_plugin_alconna import Arparma, Extension, UniMessage
from typing import Any, Dict
from arclet.alconna.exceptions import (
    ArgumentMissing,
    ParamsUnmatched
)
from nonebot.adapters import Bot, Event, Message
from nonebot import require
from nonebot_plugin_alconna.uniseg import reply_fetch

require("nonebot_plugin_alconna")

from ..nonebot_plugin_larklang import LangHelper

lang = LangHelper()



class ReplyExtension(Extension):

    @property
    def priority(self) -> int:
        return 14
    
    @property
    def id(self) -> str:
        return "lark_reply"
    
    async def message_provider(
            self,
            event: Event,
            state: Dict[Any, Any],
            bot: Bot,
            use_origin: bool = False
    ) -> Message | UniMessage | None:
        try:
            msg = event.get_message()
        except ValueError:
            return
        if not (reply := await reply_fetch(event, bot)):
            return
        uni_msg_reply = UniMessage()
        if reply.msg:
            reply_msg = reply.msg
            if isinstance(reply_msg, str):
                reply_msg = msg.__class__(reply_msg)
            uni_msg_reply = UniMessage.generate_without_reply(
                message=reply_msg,
                bot=bot
            )
        uni_msg = UniMessage.generate_without_reply(
            message=msg,
            bot=bot
        )
        uni_msg += " "
        uni_msg.extend(uni_msg_reply)
        return uni_msg

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