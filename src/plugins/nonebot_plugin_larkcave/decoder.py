import re
import traceback

from nonebot import logger
from nonebot_plugin_alconna import Image, Text, UniMessage
from nonebot_plugin_orm import async_scoped_session

from ..nonebot_plugin_larkuser import get_user
from .lang import lang
from .models import CaveData, ImageData


async def get_image(match: str, session: async_scoped_session) -> ImageData:
    image_id = match[6:-3]
    logger.debug(f"获取图片: {image_id}")
    return await session.get_one(ImageData, {"id": image_id})


def parse_text(text: str) -> Text:
    return Text(text.replace("&#91;", "[").replace("&#93;", "]"))


async def parse_content(content: str, session: async_scoped_session) -> UniMessage:
    length = 0
    message = UniMessage()
    for match in re.finditer(r"\[\[Img:\d+\.\d+\]\]\]", content):
        span = match.span()
        message.append(parse_text(content[length : span[0]]))
        try:
            message.append(Image(raw=(image := await get_image(match.group(), session)).data, name=image.name))
        except Exception:
            logger.warning(f"获取图片失败: {traceback.format_exc()}")
        length = span[1]
    message.append(parse_text(content[length:]))
    return message


async def decode_cave(cave: CaveData, session: async_scoped_session, user_id: str) -> UniMessage:
    message = UniMessage(await lang.text("render.header", user_id, cave.id))
    message.extend(await parse_content(cave.content, session))
    message.append(Text(await lang.text("render.footer", user_id, (await get_user(cave.author)).nickname)))
    return message
