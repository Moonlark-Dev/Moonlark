from datetime import datetime
from typing import Optional
from nonebot import logger
from nonebot.adapters import Bot
from nonebot.adapters import Event
from nonebot.typing import T_State
from nonebot_plugin_chat.types import CachedMessage
from nonebot_plugin_userinfo import get_user_info
from nonebot_plugin_alconna import Image, Other, Segment, UniMessage, Text, At, Reply, Reference
from nonebot_plugin_larkuser import get_user
from nonebot.exception import ActionFailed
from nonebot.adapters import Message, MessageSegment
from nonebot.adapters.onebot.v11 import Bot as OneBotV11Bot
from nonebot.adapters.onebot.v11 import Message as OneBotV11Message
from nonebot.adapters.onebot.v11 import MessageSegment as OneBotV11Segment


from .image import get_image_summary


class MessageParser:

    def __init__(self, message: UniMessage, event: Event, bot: Bot, state: T_State) -> None:
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
            description, image_id = await get_image_summary(segment, self.event, self.bot, self.state)
            if image_id:
                return f"[图片({image_id}): {description}]"
            else:
                return f"[图片: {description}]"
        elif isinstance(segment, Reply) and (segment.msg is not None or segment.id is not None):
            return await self.parse_reply(segment)
        elif isinstance(segment, Reference) and isinstance(self.bot, OneBotV11Bot) and segment.id is not None:
            return await self.parse_forawrd_message(segment.id)
        elif isinstance(segment, Other):
            return await self.parse_special_segment(segment.origin)
        else:
            return f"[特殊消息: {segment.dump()}]"

    async def parse_special_segment(self, segment: MessageSegment) -> str:
        if segment.type == "poke":
            return f"[戳一戳]"
        return f"[特殊消息: {segment}]"

    async def parse_forawrd_message(self, ref_id: str) -> str:
        if not isinstance(self.bot, OneBotV11Bot):
            return f"[合并转发: 获取信息失败（不受支持）]"
        try:
            message_list_str = await self.get_forawrd_message_list(ref_id)
        except ActionFailed as e:
            return f"[合并转发: 获取信息失败（{e}）]"
        return f"[合并转发: {message_list_str}]"

    async def get_forawrd_message_list(self, ref_id: str) -> str:
        forward = await self.bot.get_forward_msg(id=ref_id)
        message_list = [
            (
                f"[{datetime.fromtimestamp(msg['time']).strftime('%H:%M:%S')}]"
                f"[{msg['sender']['card'] or msg['sender']['nickname']}]: "
                f"{await self.get_parsed_message(msg['message'])}"
            )
            for msg in forward["messages"]
        ]
        return "\n".join(message_list)

    async def get_parsed_message(self, node_message: list[dict]) -> str:
        uni_message = await parse_dict_message(node_message, self.bot, self.event)
        return await parse_message_to_string(uni_message, self.event, self.bot, self.state)

    async def parse_mention(self, segment: At) -> str:
        user = await get_user(segment.target)
        if (not user.has_nickname()) and (user_info := await get_user_info(self.bot, self.event, segment.target)):
            nickname = user_info.user_displayname or user_info.user_name
        else:
            nickname = user.get_nickname()
        return f"@{nickname}"

    async def parse_reply(self, segment: Reply) -> str:
        logger.info(f"Reply: {segment=} {segment.msg=} {segment.id=}")
        if isinstance(segment.msg, UniMessage):
            return f"[回复: {await parse_message_to_string(segment.msg, self.event, self.bot, self.state)}]"
        elif isinstance(segment.msg, Message):
            message = UniMessage.of(message=segment.msg, bot=self.bot)

            # await message.attach_reply(self.event, self.bot)
            logger.info(f"Reply UniMessage: {message=}")
            return f"[回复: {await parse_message_to_string(message, self.event, self.bot, self.state)}]"
        elif segment.msg is not None:
            return f"[回复: {segment.msg}]"
        elif isinstance(self.bot, OneBotV11Bot):
            result = await self.bot.get_msg(message_id=int(segment.id))
            message = await parse_message_to_string(
                await parse_dict_message(result["message"], self.bot), self.event, self.bot, self.state
            )
            return f"[回复: {message}]"
        else:
            return "[回复: 消息获取失败]"


async def parse_dict_message(dict_message: list[dict], bot: Bot, event: Optional[Event] = None) -> UniMessage:
    ob11_message = OneBotV11Message()
    for segment in dict_message:
        ob11_message.append(OneBotV11Segment(**segment))
    uni_message = UniMessage.of(message=ob11_message, bot=bot)
    if event:
        await uni_message.attach_reply(event, bot)
    return uni_message


async def parse_message_to_string(message: UniMessage, event: Event, bot: Bot, state: T_State) -> str:
    parser = MessageParser(message, event, bot, state)
    return await parser.parse()


def generate_message_string(message: CachedMessage) -> str:
    return f"[{message['send_time'].strftime('%H:%M:%S')}][{message['nickname']}]({message['message_id']}): {message['content']}\n"


