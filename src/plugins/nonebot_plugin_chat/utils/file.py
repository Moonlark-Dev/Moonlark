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
import base64
import hashlib
import traceback
from pathlib import Path
from typing_extensions import TypedDict

import httpx
from nonebot import get_driver, logger, require
from nonebot.adapters import Bot, Event
from nonebot.typing import T_State
from nonebot_plugin_alconna import File
from nonebot_plugin_localstore import get_cache_dir
from nonebot_plugin_openai import fetch_message
from nonebot_plugin_openai.utils.message import generate_message, get_message, get_message_text

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

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
    # 读取文件内容并计算哈希用于缓存（内容后面还要编码，读一次就够了）
    video_bytes = file_path.read_bytes()
    file_hash = hashlib.sha256(video_bytes).hexdigest()

    # 检查缓存
    if (cache := await description_cache.get(file_hash)) is not None:
        return cache["description"]

    try:
        # 编码为 base64 内联上传（Gemini 2.0+ 不再支持外部 HTTP URL 视频输入）
        video_base64 = base64.b64encode(video_bytes).decode("utf-8")
        video_data_url = f"data:video/mp4;base64,{video_base64}"

        # 复用 bilibili 的提示词
        messages = [
            await get_message("system", "bilibili/system.md.jinja"),
            generate_message(
                [
                    {
                        "type": "text",
                        "text": await get_message_text("bilibili/user.md.jinja", title=file_name, description=""),
                    },
                    {"type": "video_url", "video_url": {"url": video_data_url}},
                ],
                role="user",
            ),
        ]

        result = await fetch_message(messages=messages, identify="Video File Describe")

        # 缓存结果
        cache_data: FileCacheData = {"description": result}
        await description_cache.set(file_hash, cache_data)

        return result
    except Exception as e:
        logger.warning(f"视频描述失败: {e}")
        logger.warning(traceback.format_exc())
        return "视频分析失败"


from nonebot.adapters.onebot.v11 import Bot as OneBotV11Bot


def _remove_file_quietly(path: Path) -> None:
    """尽力删除一个缓存文件，失败时只记录日志（清理动作不应打断业务流程）"""
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        logger.warning(f"清理 {path} 时出现错误: {e}")


async def get_file_url(file_id: str, bot: OneBotV11Bot) -> str:
    return (await bot.call_api("get_file", file_id=file_id))["url"]


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
    file_url = segment.url
    file_type = "file"

    if file_url is None and isinstance(bot, OneBotV11Bot) and segment.id:
        file_url = await get_file_url(segment.id, bot)
    elif not file_url:
        file_url = ""

    # 判断是否为视频文件
    if is_video_file(file_name):
        file_type = "video"
        description = "正在分析视频内容..."

        # 尝试获取视频描述
        if file_url:
            # 下载视频文件
            file_hash = hashlib.sha256(file_url.encode()).hexdigest()[:16]
            temp_path = FILE_CACHE_DIR / f"temp_{file_hash}{Path(file_name).suffix}"

            try:
                # 先移除可能残留的下载临时文件（上次下载中断留下的残档会被误当缓存复用）
                _remove_file_quietly(temp_path)
                await _download_file(file_url, temp_path)

                description = await describe_video(temp_path, file_name, event.get_user_id())
            except Exception as e:
                logger.warning(f"获取视频文件失败: {e}")
                description = "无法获取视频文件"
            finally:
                # 清理临时文件
                _remove_file_quietly(temp_path)

    else:
        # 非视频文件
        ext = Path(file_name).suffix.lower()
        description = f"{ext or '未知'} 文件"

    return file_type, file_name, description


# 导出供其他模块使用
__all__ = ["get_file_summary", "is_video_file", "describe_video"]


@scheduler.scheduled_job("cron", hour=2, minute=35, id="cleanup_chat_file_cache")
async def _cleanup_file_cache() -> None:
    """清理文件缓存目录中残留的下载临时文件与旧版视频副本

    FILE_CACHE_DIR 目前只有两个写入方：
    - get_file_summary 的下载临时文件（temp_*，正常路径会清理，中断时残留）
    - 旧版 describe_video 复制的视频副本（video_*，改用 base64 内联后已不再写入，仅存量残留）
    """
    from ..core.session import groups

    for session in groups.values():
        if session.processor.openai_messages.fetcher_lock.locked():
            logger.debug("跳过清理 chat 文件缓存：有会话正在处理")
            return

    if not FILE_CACHE_DIR.exists():
        return

    count = 0
    for file in FILE_CACHE_DIR.iterdir():
        if file.is_file() and (file.name.startswith("temp_") or file.name.startswith("video_")):
            try:
                file.unlink()
                count += 1
            except OSError as e:
                logger.warning(f"清理 {file} 时出现错误: {e}")

    logger.info(f"已清理 {count} 个 chat 文件缓存文件")
