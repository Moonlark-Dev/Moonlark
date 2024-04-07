from typing import Any, Dict
from nonebot.adapters import Bot, Event, Message
from nonebot.typing import T_State
from nonebot_plugin_alconna import Extension, UniMessage
from nonebot_plugin_alconna.uniseg import reply_fetch

class ReplyExtension(Extension):

    @property
    def priority(self) -> int:
        return 14
    
    @property
    def id(self) -> str:
        return "reply"
    
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