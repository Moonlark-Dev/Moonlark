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
import hashlib
import os
import traceback
from pathlib import Path
from typing import TypedDict

import httpx
from nonebot import get_driver, logger
from nonebot.adapters import Bot, Event
from nonebot.typing import T_State
from nonebot_plugin_alconna import File
from nonebot_plugin_localstore import get_cache_dir
from nonebot_plugin_openai import fetch_message
from nonebot_plugin_openai.utils.message import generate_message

from ..config import config
from ..lang import lang
from .cache import AsyncCache

# 视频文件扩展名
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm", ".m4v", ".3gp"}

# 文件缓存目录
FILE_CACHE_DIR: Path = get_cache_dir("nonebot_plugin_chat") / "files"

# 文件描述缓存
description_cache: AsyncCache


class FileCacheData(TypedDict):
    """文件缓存数据结构"""

    description: str  # 生成的描述
    file_id: str  # 临时文件 ID
    file_path: Path  # 文件本地路径


@get_driver().on_startup
async def _() -> None:
    global description_cache
    description_cache = AsyncCache(600)  # 10 分钟过期
    # 确保缓存目录存在
    if not FILE_CACHE_DIR.exists():
        FILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def is_video_file(file_name: str) -> bool:
    """
    判断文件是否为视频文件

    Args:
        file_name: 文件名

    Returns:
        bool: 是否为视频文件
    """
    ext = Path(file_name).suffix.lower()
    return ext in VIDEO_EXTENSIONS


async def _download_file(url: str, path: Path) -> None:
    """
    下载文件到本地

    Args:
        url: 文件 URL
        path: 本地保存路径
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)


async def describe_video(file_path: Path, file_name: str, user_id: str) -> str:
    """
    使用 AI 描述视频内容（复用 bilibili 视频总结的提示词）

    Args:
        file_path: 视频文件本地路径
        file_name: 原始文件名
        user_id: 用户 ID

    Returns:
        str: 视频描述
    """
    # 计算文件哈希用于缓存
    file_hash = hashlib.sha256(open(file_path, "rb").read()).hexdigest()

    # 检查缓存
    if (cache := await description_cache.get(file_hash)) is not None:
        return cache["description"]

    # 生成外部访问 URL
    file_id = f"video_{file_hash[:16]}{Path(file_name).suffix}"
    cache_file_path = FILE_CACHE_DIR / file_id

    # 复制文件到缓存目录（如果不在那里）
    if not cache_file_path.exists():
        import shutil

        shutil.copy(file_path, cache_file_path)

    external_url = f"{config.moonlark_api_base}/chat/files/{file_id}"

    try:
        # 复用 bilibili 的提示词
        messages = [
            generate_message(
                await lang.text("bilibili.summary_system_prompt", user_id),
                role="system",
            ),
            generate_message(
                [
                    {"type": "text", "text": await lang.text("bilibili.summary_user_prompt", user_id, file_name, "")},
                    {"type": "video_url", "video_url": {"url": external_url}},
                ],
                role="user",
            ),
        ]

        result = await fetch_message(messages=messages, identify="Video File Describe")

        # 缓存结果
        cache_data: FileCacheData = {
            "description": result,
            "file_id": file_id,
            "file_path": cache_file_path,
        }
        await description_cache.set(file_hash, cache_data)

        return result
    except Exception as e:
        logger.warning(f"视频描述失败: {e}")
        logger.warning(traceback.format_exc())
        return "视频分析失败"


async def get_file_summary(segment: File, event: Event, bot: Bot, state: T_State) -> tuple[str, str, str]:
    """
    获取文件摘要信息

    Args:
        segment: 文件消息段
        event: 事件对象
        bot: Bot 对象
        state: 状态字典

    Returns:
        tuple[str, str, str]: (文件类型, 文件名, 描述)
    """
    file_name = segment.name or "未知文件"
    file_url = segment.url or ""
    file_type = "file"

    # 判断是否为视频文件
    if is_video_file(file_name):
        file_type = "video"
        description = "正在分析视频内容..."

        # 尝试获取视频描述
        if file_url:
            try:
                # 下载视频文件
                file_hash = hashlib.sha256(file_url.encode()).hexdigest()[:16]
                temp_path = FILE_CACHE_DIR / f"temp_{file_hash}{Path(file_name).suffix}"

                if not temp_path.exists():
                    await _download_file(file_url, temp_path)

                description = await describe_video(temp_path, file_name, event.get_user_id())

                # 清理临时文件
                if temp_path.exists():
                    os.remove(temp_path)

            except Exception as e:
                logger.warning(f"获取视频文件失败: {e}")
                description = "无法获取视频文件"
    else:
        # 非视频文件
        ext = Path(file_name).suffix.lower()
        description = f"{ext or '未知'} 文件"

    return file_type, file_name, description


# 导出供其他模块使用
__all__ = ["get_file_summary", "is_video_file", "describe_video"]
