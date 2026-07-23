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

"""辅助函数：会话状态判断、消息序列化、会话名缓存等"""

import time
from typing import Any, Optional
from nonebot.log import logger


class SessionNameCache:
    """会话名称缓存，避免每 2 秒异步调用 get_session_name()。"""

    def __init__(self, ttl: float = 10.0):
        self._cache: dict[str, tuple[str, float]] = {}  # session_id -> (name, timestamp)

    def get(self, session_id: str) -> Optional[str]:
        """获取缓存的会话名称（如果未过期）。"""
        entry = self._cache.get(session_id)
        if entry and time.monotonic() - entry[1] < 10.0:
            return entry[0]
        return None

    def set(self, session_id: str, name: str):
        self._cache[session_id] = (name, time.monotonic())

    def remove(self, session_id: str):
        self._cache.pop(session_id, None)

    def clear(self):
        self._cache.clear()


# 全局会话名缓存实例（TTL 10 秒）
session_name_cache = SessionNameCache()


async def get_cached_session_name(session: Any, session_id: str) -> str:
    """获取会话名称，优先使用缓存。"""
    cached = session_name_cache.get(session_id)
    if cached:
        return cached

    name = session_id
    try:
        resolved = await session.get_session_name()
        name = resolved or session_id
    except Exception as exc:
        logger.warning(f"[ChatMonitor] 获取会话名失败 {session_id}: {exc}")
    session_name_cache.set(session_id, name)
    return name


def get_session_state(session: Any) -> str:
    """获取会话的当前状态：parsing / replying / idle"""
    if session.processor.openai_messages.fetcher_lock.locked():
        return "replying"
    if session.message_queue:
        return "parsing"
    return "idle"


def get_session_last_activity(session: Any) -> Optional[str]:
    """获取会话的最后活动时间"""
    if session.cached_messages:
        return session.cached_messages[-1]["send_time"].isoformat()
    if hasattr(session, "last_activate") and session.last_activate:
        return session.last_activate.isoformat()
    return None


def serialize_cached_message(msg: dict) -> dict:
    """序列化一条缓存消息，images 只返回个数以避免过大。"""
    return {
        "content": msg.get("content", ""),
        "nickname": msg.get("nickname", ""),
        "user_id": msg.get("user_id", ""),
        "platform_user_id": msg.get("platform_user_id", ""),
        "send_time": msg.get("send_time").isoformat() if msg.get("send_time") else None,
        "self": msg.get("self", False),
        "message_id": msg.get("message_id", ""),
        "image_count": len(msg.get("images", [])),
    }
