#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

import re
import traceback
import zlib

from nonebot import logger
from nonebot_plugin_alconna import Image, Text, UniMessage
from nonebot_plugin_orm import async_scoped_session

from nonebot_plugin_larkuser import get_user
from ..lang import lang
from ..models import CaveData, ImageData, CaveImage


async def get_image(image_id: str, session: async_scoped_session) -> CaveImage:
    logger.debug(f"获取图片: {image_id}")
    image_data = await session.get_one(ImageData, float(image_id))
    if image_data.image_data is None:
        raise ValueError(f"图片数据为空: {image_id}")
    return CaveImage(id_=image_data.id, data=zlib.decompress(image_data.image_data), name=image_data.name)


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
    new_message = UniMessage()
    for segment in message:
        if isinstance(segment, Text):
            for line in segment.text.splitlines():
                new_message.append(Text(f"{line[::-1]}\n"))
        else:
            new_message.append(segment)
    return new_message


async def decode_cave(
    cave: CaveData, session: async_scoped_session, user_id: str, use_special: bool = False
) -> UniMessage:
    message = UniMessage(await lang.text("render.header", user_id, cave.id))
    message.extend(await parse_content(cave.content, session))
    message.append(Text(await lang.text("render.footer", user_id, (await get_user(cave.author)).get_nickname())))
    if use_special:
        message = reverse_cave_message(message)
    return message
