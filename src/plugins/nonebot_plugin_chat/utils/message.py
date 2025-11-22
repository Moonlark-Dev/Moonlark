
from nonebot.adapters import Bot
from nonebot.adapters import Event
from nonebot.typing import T_State
from nonebot_plugin_userinfo import get_user_info
from nonebot_plugin_alconna import Image, Segment, UniMessage, Text, At, Reply, Reference
from nonebot_plugin_orm import get_session
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils import get_group_id, get_user_id
from nonebot.exception import ActionFailed
from nonebot.adapters import Message

from nonebot.adapters.onebot.v11 import Bot as OneBotV11Bot


from .image import get_image_summary


class MessageParser:

    def __init__(self, message: UniMessage, event: Event, bot: Bot, state: T_State) -> str:
        self.message = message
        self.event = event
        self.bot = bot
        self.state = state
    
    async def parse(self) -> str:
        return "".join([await self.parse_segment(segment) for segment in self.message])

    async def parse_segment(self, segment: Segment) -> str:
        if isinstance(segment, Text):
            return segment.text
        elif isinstance(segment, At):
            return await self.parse_mention(segment)
        elif isinstance(segment, Image):
            return f"[图片: {await get_image_summary(segment, self.event, self.bot, self.state)}]"
        elif isinstance(segment, Reply) and segment.msg is not None:
            return await self.parse_reply(segment)
        elif isinstance(segment, Reference) and isinstance(self.bot, OneBotV11Bot) and segment.id is not None:
            return f"[合并转发({segment.id}): ]"
        else:
            return f"[特殊消息: {segment.dump()}]"
    
    async def parse_forawrd_message(self, ref_id: str) -> str:
        if not isinstance(self.bot, OneBotV11Bot):
            return f"[合并转发({ref_id}): 获取信息失败]"
        try:
            forward = await self.bot.get_forward_msg(id=ref_id)
        except ActionFailed as e:
            return f"[合并转发({ref_id}): 获取信息失败: {e}]"
        return f"[合并转发({ref_id}): 获取信息失败]"


    async def parse_mention(self, segment: At) -> str:
        user = await get_user(segment.target)
        if (not user.has_nickname()) and (user_info := await get_user_info(self.bot, self.event, segment.target)):
            nickname = user_info.user_displayname or user_info.user_name
        else:
            nickname = user.get_nickname()
        return f"@{nickname}"

    async def parse_reply(self, segment: Reply) -> str:
        if isinstance(segment.msg, UniMessage):
            return f"[回复: {await parse_message_to_string(segment.msg, self.event, self.bot, self.state)}]"
        elif isinstance(segment.msg, Message):
            return f"[回复: {await parse_message_to_string(UniMessage.generate_without_reply(message=segment.msg), self.event, self.bot, self.state)}]"
        else:
            return f"[回复: {segment.msg}]"





async def parse_message_to_string(message: UniMessage, event: Event, bot: Bot, state: T_State) -> str:
    parser = MessageParser(message, event, bot, state)
    return await parser.parse()