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

import asyncio
import io
from typing import Optional, Tuple

import imagehash
from PIL import Image
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select

from ..models import Sticker


def calculate_perceptual_hash(image_data: bytes) -> str:
    """
    计算图片的感知哈希值

    Args:
        image_data: 图片的字节数据

    Returns:
        感知哈希的十六进制字符串，如果计算失败则返回空字符串
    """
    try:
        img = Image.open(io.BytesIO(image_data))
        # 使用 average hash 算法，哈希大小为 16x16 以提高精度
        hash_value = imagehash.average_hash(img, hash_size=16)
        return str(hash_value)
    except Exception:
        return ""


def compare_hash(hash1: str, hash2: str) -> float:
    """
    比较两个感知哈希的相似度

    Args:
        hash1: 第一个哈希值
        hash2: 第二个哈希值

    Returns:
        相似度分数 (0-1)，1 表示完全相同
    """
    if not hash1 or not hash2:
        return 0.0
    try:
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)
        # 计算汉明距离，转换为相似度分数
        # hash_size=16 时，最大距离为 256 (16*16)
        max_distance = len(hash1) * 4  # 每个十六进制字符代表4位
        distance = h1 - h2
        similarity = 1 - (distance / max_distance)
        return max(0.0, similarity)
    except Exception:
        return 0.0


async def check_sticker_duplicate(
    image_data: bytes, session: async_scoped_session, similarity_threshold: float = 0.98
) -> Tuple[bool, Optional[Sticker], float]:
    """
    检查表情包是否与已存在的表情包重复

    Args:
        image_data: 待检查的图片字节数据
        session: 数据库会话
        similarity_threshold: 相似度阈值，默认为 0.98

    Returns:
        元组 (是否重复, 重复的表情包对象或None, 相似度分数)
    """
    # 在线程池中计算感知哈希（避免阻塞事件循环）
    posting_hash = await asyncio.get_running_loop().run_in_executor(None, calculate_perceptual_hash, image_data)

    if not posting_hash:
        # 无法计算哈希，视为不重复
        return False, None, 0.0

    # 获取所有已存储表情包的哈希值
    sticker_list = (await session.scalars(select(Sticker).where(Sticker.p_hash != None))).all()

    # 比较哈希值
    for sticker in sticker_list:
        if not sticker.p_hash:
            continue

        similarity = compare_hash(posting_hash, sticker.p_hash)

        # 相似度达到阈值则视为重复
        if similarity >= similarity_threshold:
            return True, sticker, similarity

    return False, None, 0.0


async def calculate_hash_async(image_data: bytes) -> str:
    """
    异步计算图片的感知哈希值

    Args:
        image_data: 图片的字节数据

    Returns:
        感知哈希的十六进制字符串
    """
    return await asyncio.get_running_loop().run_in_executor(None, calculate_perceptual_hash, image_data)
