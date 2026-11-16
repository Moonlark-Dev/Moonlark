#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
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
from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Image, Text, UniMessage
from nonebot_plugin_orm import async_scoped_session

from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils import create_image_markdown, escape_markdown

from ..lang import lang
from ..models import CaveData, ImageData, CaveImage

IMAGE_PATTERN = re.compile(r"\[\[Img:\d+\.\d+]]]")


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
    for match in IMAGE_PATTERN.finditer(content):
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
    message = UniMessage([Text(await lang.text("render.header", user_id, cave.id)), Text("\n")])
    message.extend(await parse_content(cave.content, session))
    message.append(Text(await lang.text("render.footer", user_id, (await get_user(cave.author)).get_nickname())))
    if use_special:
        message = reverse_cave_message(message)
    return message


def _escape_cave_text(text: str, use_special: bool = False) -> str:
    """把回声洞文本转成 QQ Markdown 内容

    ``use_special`` 与普通消息的倒序模式一样逐行倒序；随后还原投稿时编码的方括号，
    并转义 Markdown 特殊字符，避免投稿内容里的 ``*``、``[`` 等破坏排版。
    """
    text = text.replace("&#91;", "[").replace("&#93;", "]")
    if use_special:
        text = "".join(f"{line[::-1]}\n" for line in text.splitlines())
    return escape_markdown(text)


async def parse_content_markdown(
    content: str, session: async_scoped_session, bot: QQBot, use_special: bool = False
) -> str:
    """解析回声洞正文，把图片内嵌为 QQ Markdown 图片语法

    普通消息里的图片会被 QQ 排到消息最前面，转成 Markdown 后才能让图片保持在投稿正文中的
    位置。图片会先上传到 QQ 素材库；读取或上传失败时抛出异常，由调用方回退成普通消息。
    """
    parts: list[str] = []
    length = 0
    for match in IMAGE_PATTERN.finditer(content):
        span = match.span()
        parts.append(_escape_cave_text(content[length : span[0]], use_special))
        image = await get_image_by_match(match.group(), session)
        parts.append(await create_image_markdown(image.data, bot))
        length = span[1]
    parts.append(_escape_cave_text(content[length:], use_special))
    return "".join(parts)


async def decode_cave_markdown(
    cave: CaveData, session: async_scoped_session, user_id: str, bot: QQBot, use_special: bool = False
) -> str:
    """把回声洞解码为 QQ Markdown 文本，图片内嵌在正文中的原位置"""
    header = await lang.text("render.header", user_id, cave.id)
    content = await parse_content_markdown(cave.content, session, bot, use_special)
    footer = await lang.text("render.footer", user_id, (await get_user(cave.author)).get_nickname())
    return _escape_cave_text(f"{header}\n", use_special) + content + _escape_cave_text(footer, use_special)


async def build_cave_message(
    cave: CaveData,
    session: async_scoped_session,
    user_id: str,
    bot: Bot,
    use_special: bool = False,
    prefix: str = "",
    suffix: str = "",
) -> UniMessage:
    """构造回声洞展示消息

    QQ 官方机器人下改用 Markdown 发送，让投稿正文里的图片保持原位；其余适配器保持原来的
    分段消息。Markdown 渲染失败（如图片上传素材库失败）时同样回退为分段消息，避免整条
    回声洞发不出去。
    """
    if isinstance(bot, QQBot):
        try:
            markdown = prefix + await decode_cave_markdown(cave, session, user_id, bot, use_special) + suffix
            return UniMessage().style(markdown, "markdown")
        except Exception:
            logger.warning(f"回声洞 Markdown 渲染失败，回退为普通消息: {traceback.format_exc()}")
    message = UniMessage()
    if prefix:
        message.append(Text(prefix))
    message.extend(await decode_cave(cave, session, user_id, use_special))
    if suffix:
        message.append(Text(suffix))
    return message
