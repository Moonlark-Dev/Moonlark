from datetime import datetime
from typing import Optional
from nonebot import logger
from nonebot.adapters import Bot
from nonebot.adapters import Event
from nonebot.typing import T_State
from nonebot_plugin_chat.lang import lang
from nonebot_plugin_chat.types import CachedMessage
from nonebot_plugin_larkuser.utils.nickname import get_nickname
from nonebot_plugin_userinfo import get_user_info
from nonebot_plugin_alconna import Image, Other, Segment, UniMessage, Text, At, Reply, Reference, File, image_fetch
from nonebot_plugin_larkuser import get_user
from nonebot.exception import ActionFailed
from nonebot.adapters import Message, MessageSegment
from nonebot.adapters.onebot.v11 import Bot as OneBotV11Bot
from nonebot.adapters.onebot.v11 import Message as OneBotV11Message
from nonebot.adapters.onebot.v11 import MessageSegment as OneBotV11Segment


from .image import generate_image_id, get_image_summary
from .file import get_file_summary


class MessageParser:

    def __init__(self, message: UniMessage, event: Event, bot: Bot, state: T_State, lang_str: str, describe_image: bool = True) -> None:
        self.message = message
        self.event = event
        self.describe_image = describe_image
        self.user_id = lang_str
        self.bot = bot
        self.state = state
        self.images = []

    async def parse(self) -> str:
        return "".join([await self.parse_segment(segment) for segment in self.message])

    async def get_image_description(self, image: Image) -> str:
        description, image_id = await get_image_summary(image, self.event, self.bot, self.state)
        if image_id:
            return await lang.text("parser.image_with_id", self.user_id, image_id, description)
        else:
            return await lang.text("parser.image", self.user_id, description)
        
    async def parse_image(self, image: Image) -> str:
        if self.describe_image:
            return await self.get_image_description(image)
        else:
            image_raw = await image_fetch(self.event, self.bot, self.state, image)
            if not isinstance(image_raw, bytes):
                return await lang.text("parser.image_failed", self.user_id)
            image_id = await generate_image_id(image_raw)
            self.images.append(image_raw)
            return await lang.text("parser.image_without_desc", self.user_id, image_id)

    async def parse_segment(self, segment: Segment) -> str:
        if isinstance(segment, Text):
            return segment.text
        elif isinstance(segment, At):
            return await self.parse_mention(segment)
        elif isinstance(segment, Image):
            return await self.parse_image(segment)
        elif isinstance(segment, File):
            file_type, file_name, description = await get_file_summary(segment, self.event, self.bot, self.state)
            if file_type == "video":
                return await lang.text("parser.video", self.user_id, file_name, description)
            else:
                return await lang.text("parser.file", self.user_id, file_name, description)
        elif isinstance(segment, Reply) and (segment.msg is not None or segment.id is not None):
            return await self.parse_reply(segment)
        elif isinstance(segment, Reference) and isinstance(self.bot, OneBotV11Bot) and segment.id is not None:
            return await self.parse_forawrd_message(segment.id)
        elif isinstance(segment, Other):
            return await self.parse_special_segment(segment.origin)
        else:
            return await lang.text("parser.other", self.user_id, segment.dump())

    async def parse_special_segment(self, segment: MessageSegment) -> str:
        if segment.type == "poke":
            return await lang.text("parser.poke", self.user_id)
        return await lang.text("parser.other", self.user_id, segment)

    async def parse_forawrd_message(self, ref_id: str) -> str:
        if not isinstance(self.bot, OneBotV11Bot):
            return await lang.text("parser.forward.not_supported", self.user_id)
        try:
            message_list_str = await self.get_forawrd_message_list(ref_id)
        except ActionFailed as e:
            return await lang.text("parser.forward.failed", self.user_id, e)
        return await lang.text("parser.forward.forward", self.user_id, message_list_str)

    async def get_forawrd_message_list(
        self, ref_id: str
    ) -> str:  # 定义一个异步方法，获取转发消息列表，接收一个ref_id参数，返回字符串类型
        forward = await self.bot.get_forward_msg(id=ref_id)  # 通过机器人获取转发消息，使用ref_id作为标识
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
        return await parse_message_to_string(uni_message, self.event, self.bot, self.state, self.user_id)

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
            msg = await parse_message_to_string(segment.msg, self.event, self.bot, self.state, self.user_id)
            return await lang.text("parser.reply", self.user_id, msg)
        elif isinstance(segment.msg, Message):
            message = UniMessage.of(message=segment.msg, bot=self.bot)
            logger.info(f"Reply UniMessage: {message=}")
            msg = await parse_message_to_string(message, self.event, self.bot, self.state, self.user_id)
            return await lang.text("parser.reply", self.user_id, msg)
        elif segment.msg is not None:
            return await lang.text("parser.reply", self.user_id, segment.msg)
        elif isinstance(self.bot, OneBotV11Bot):
            result = await self.bot.get_msg(message_id=int(segment.id))
            message = await parse_message_to_string(
                await parse_dict_message(result["message"], self.bot), self.event, self.bot, self.state, self.user_id
            )
            sender_nickname = await get_nickname(str(result["sender"]["user_id"]), self.bot, self.event)
            return await lang.text("parser.reply_with_sender", self.user_id, message, sender_nickname)
        else:
            return await lang.text("parser.reply_failed", self.user_id, segment.id)


async def parse_dict_message(dict_message: list[dict], bot: Bot, event: Optional[Event] = None) -> UniMessage:
    ob11_message = OneBotV11Message()
    for segment in dict_message:
        ob11_message.append(OneBotV11Segment(**segment))
    uni_message = UniMessage.of(message=ob11_message, bot=bot)
    if event:
        await uni_message.attach_reply(event, bot)
    return uni_message


async def parse_message_to_string(message: UniMessage, event: Event, bot: Bot, state: T_State, lang_str: str) -> str:
    parser = MessageParser(message, event, bot, state, lang_str)
    return await parser.parse()

# async def parse_message_without_parsing_image(message: UniMessage, event: Event, bot: Bot, state: T_State, lang_str: str) -> tuple[str, list[bytes]]:
#     parser = MessageParser(message, event, bot, state, lang_str, False)
#     return (await parser.parse()), parser.images

def generate_message_string(message: CachedMessage) -> str:
    return f"[{message['send_time'].strftime('%H:%M:%S')}][{message['nickname']}]({message['message_id']}): {message['content']}\n"
