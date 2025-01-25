import re
import traceback
import zlib

import aiofiles
from nonebot import logger
from nonebot_plugin_localstore import get_data_dir
from nonebot_plugin_alconna import Image, Text, UniMessage
from nonebot_plugin_orm import async_scoped_session

from ..nonebot_plugin_larkuser import get_user
from .lang import lang
from .models import CaveData, ImageData, CaveImage

data_dir = get_data_dir("nonebot_plugin_larkcave")


async def get_image(image_id: str, session: async_scoped_session) -> CaveImage:
    logger.debug(f"获取图片: {image_id}")
    image_data = await session.get_one(ImageData, float(image_id))
    async with aiofiles.open(data_dir.joinpath(image_data.file_id), "rb") as f:
        return CaveImage(id_=image_data.id, data=zlib.decompress(await f.read()), name=image_data.name)


async def get_image_by_match(match: str, session: async_scoped_session) -> CaveImage:
    image_id = match[6:-3]
    return await get_image(image_id, session)


def parse_text(text: str) -> Text:
    return Text(text.replace("&#91;", "[").replace("&#93;", "]"))


async def parse_content(content: str, session: async_scoped_session) -> UniMessage:
    length = 0
    message = UniMessage()
    for match in re.finditer(r"\[\[Img:\d+\.\d+]]]", content):
        span = match.span()
        message.append(parse_text(content[length : span[0]]))
        try:
            message.append(Image(raw=(image := await get_image_by_match(match.group(), session)).data, name=image.name))
        except Exception:
            logger.warning(f"获取图片失败: {traceback.format_exc()}")
        length = span[1]
    message.append(parse_text(content[length:]))
    return message

def reverse_cave_message(message: UniMessage) -> UniMessage:
    for segment in message:
        if isinstance(segment, Text):
            segment.text = segment.text[::-1].replace("\\", "__LOVE_XXTG666__").replace("/", "\\").replace("__LOVE_XXTG666__", "/")
    return message


async def decode_cave(cave: CaveData, session: async_scoped_session, user_id: str, use_special: bool = False) -> UniMessage:
    message = UniMessage(await lang.text("render.header", user_id, cave.id))
    message.extend(await parse_content(cave.content, session))
    message.append(Text(await lang.text("render.footer", user_id, (await get_user(cave.author)).get_nickname())))
    if use_special:
        message = reverse_cave_message(message)
    return message
