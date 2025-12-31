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
import base64
import datetime
import hashlib
import traceback
from typing import Optional, TypedDict

from nonebot import logger
from nonebot.adapters import Bot
from nonebot.internal.adapter import Event
from nonebot.typing import T_State
from nonebot_plugin_alconna import Image, image_fetch

from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_openai.utils.message import generate_message
from nonebot import get_driver

from ..lang import lang
from .cache import AsyncCache


class ImageCacheData(TypedDict):
    """图片缓存数据结构"""
    description: str  # VLM 生成的描述
    image_id: str  # 临时图片 ID
    raw: bytes  # 二进制图片数据


# 图片描述缓存（使用 hash 作为 key）
image_cache: AsyncCache
# 图片 ID 缓存（使用 image_id 作为 key，用于快速查找）
image_id_cache: AsyncCache
# 图片 ID 计数器
image_id_counter: int = 0


@get_driver().on_startup
async def _() -> None:
    global image_cache, image_id_cache
    image_cache = AsyncCache(600)  # 10 分钟过期
    image_id_cache = AsyncCache(600)  # 10 分钟过期


async def request_describe_image(image: bytes, user_id: str) -> tuple[str, str]:
    """
    获取图片描述并分配临时 ID
    
    Args:
        image: 图片二进制数据
        user_id: 用户 ID
        
    Returns:
        tuple[str, str]: (描述, 临时图片ID)
    """
    global image_id_counter
    
    img_hash = hashlib.sha256(image).hexdigest()
    
    # 检查是否已缓存
    if (cache := await image_cache.get(img_hash)) is not None:
        return cache["description"], cache["image_id"]
    
    # 生成新的图片 ID
    image_id_counter += 1
    image_id = f"img_{image_id_counter}"
    
    # 调用 VLM 获取描述
    image_base64 = base64.b64encode(image).decode("utf-8")
    messages = [
        generate_message(
            await lang.text("prompt_group.image_describe_system", user_id, datetime.datetime.now().isoformat()),
            "system",
        ),
        generate_message(
            [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                {"type": "text", "text": await lang.text("prompt_group.image_describe_user", user_id)},
            ],
            "user",
        ),
    ]

    try:
        summary = (await fetch_message(messages, identify="Image Describe")).strip()
    except Exception as e:
        logger.warning(traceback.format_exc())
        summary = f"暂无信息 ({e})"
    
    # 缓存数据
    cache_data: ImageCacheData = {
        "description": summary,
        "image_id": image_id,
        "raw": image,
    }
    await image_cache.set(img_hash, cache_data)
    await image_id_cache.set(image_id, cache_data)
    
    return summary, image_id


async def get_image_summary(segment: Image, event: Event, bot: Bot, state: T_State) -> tuple[str, str]:
    """
    获取图片摘要和临时 ID
    
    Args:
        segment: 图片消息段
        event: 事件对象
        bot: Bot 对象
        state: 状态字典
        
    Returns:
        tuple[str, str]: (描述, 临时图片ID)，如果获取失败返回 ("暂无信息", "")
    """
    if not isinstance(image := await image_fetch(event, bot, state, segment), bytes):
        return "暂无信息", "0"
    return await request_describe_image(image, event.get_user_id())


async def get_image_by_id(image_id: str) -> Optional[ImageCacheData]:
    """
    通过临时 ID 获取图片缓存数据
    
    Args:
        image_id: 临时图片 ID
        
    Returns:
        ImageCacheData 或 None（如果未找到或已过期）
    """
    return await image_id_cache.get(image_id)
