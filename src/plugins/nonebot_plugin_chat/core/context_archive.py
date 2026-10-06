"""上下文归档：把长期没有新消息的 context 从数据库搬到本地 json

每天上午 7:00 由 ``core/session/__init__.py`` 的定时任务调用。最后一条消息超过
三天（:data:`ARCHIVE_AFTER_DAYS`）的 context 会被从 ``nonebot_plugin_chat_contextmessage``
删除，并以 json 的形式保存在 LocalStore 的数据目录下。

这个功能不属于 :class:`~nonebot_plugin_chat.core.context.ChatContext`：归档的对象是
数据库里所有会话的所有 context，而 ChatContext 只关心自己那一个。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import aiofiles
import nonebot_plugin_localstore as store
from nonebot.log import logger
from nonebot_plugin_orm import get_session
from sqlalchemy import delete, func, select

from ..models import ChatContextMessage

# 最后一条消息超过该天数的 context 会被归档
ARCHIVE_AFTER_DAYS = 3
# 归档目录（LocalStore 数据目录下的子目录）
ARCHIVE_DIR_NAME = "context_archive"

_SAFE_NAME = re.compile(r"[^0-9A-Za-z_.-]+")


@dataclass
class ContextArchiveResult:
    """归档执行结果"""

    archived: list[tuple[str, int]] = field(default_factory=list)
    failed: list[tuple[str, int]] = field(default_factory=list)

    @property
    def archived_count(self) -> int:
        return len(self.archived)


def _archive_dir():
    directory = store.get_data_dir("nonebot_plugin_chat") / ARCHIVE_DIR_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _archive_path(session_id: str, context_index: int):
    safe_session_id = _SAFE_NAME.sub("_", session_id) or "session"
    return _archive_dir() / safe_session_id / f"{context_index}.json"


def _serialize_row(row: ChatContextMessage) -> dict:
    return {
        "index": row.index,
        "block_id": row.block_id,
        "role": row.role,
        "sub_type": row.sub_type,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "content": row.content,
        "data": row.data,
        "tool_calls": row.tool_calls,
        "tool_call_id": row.tool_call_id,
        "trigger_type": row.trigger_type,
        "request_id": row.request_id,
    }


async def _active_context_indexes() -> dict[str, int]:
    """内存中仍然活跃的会话及其当前 context index（不参与归档）"""
    from .session import groups

    active: dict[str, int] = {}
    for session_id, session in groups.items():
        try:
            active[session_id] = session.processor.openai_messages.context.context_index
        except Exception:  # pragma: no cover - 会话尚未初始化完成
            continue
    return active


async def _list_expired_contexts(cutoff: datetime) -> list[tuple[str, int]]:
    async with get_session() as db_session:
        result = await db_session.execute(
            select(
                ChatContextMessage.session_id,
                ChatContextMessage.context_index,
                func.max(ChatContextMessage.timestamp),
            ).group_by(ChatContextMessage.session_id, ChatContextMessage.context_index)
        )
        return [
            (session_id, int(context_index))
            for session_id, context_index, last_timestamp in result.all()
            if last_timestamp is not None and last_timestamp < cutoff
        ]


async def _load_context(session_id: str, context_index: int) -> list[ChatContextMessage]:
    async with get_session() as db_session:
        result = await db_session.scalars(
            select(ChatContextMessage)
            .where(
                ChatContextMessage.session_id == session_id,
                ChatContextMessage.context_index == context_index,
            )
            .order_by(ChatContextMessage.index)
        )
        return list(result)


async def _delete_context(session_id: str, context_index: int) -> None:
    async with get_session() as db_session:
        await db_session.execute(
            delete(ChatContextMessage).where(
                ChatContextMessage.session_id == session_id,
                ChatContextMessage.context_index == context_index,
            )
        )
        await db_session.commit()


async def archive_context(session_id: str, context_index: int) -> Optional[object]:
    """把单个 context 归档到本地 json 并从数据库删除

    Returns:
        归档文件的路径；context 为空时返回 None
    """
    rows = await _load_context(session_id, context_index)
    if not rows:
        return None
    path = _archive_path(session_id, context_index)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "context_index": context_index,
        "archived_at": datetime.now().isoformat(),
        "message_count": len(rows),
        "messages": [_serialize_row(row) for row in rows],
    }
    async with aiofiles.open(path, "w", encoding="utf-8") as file:
        await file.write(json.dumps(payload, ensure_ascii=False, indent=2))
    await _delete_context(session_id, context_index)
    return path


async def archive_expired_contexts(now: Optional[datetime] = None) -> ContextArchiveResult:
    """归档所有最后一条消息超过三天的 context"""
    cutoff = (now or datetime.now()) - timedelta(days=ARCHIVE_AFTER_DAYS)
    result = ContextArchiveResult()
    active = await _active_context_indexes()
    for session_id, context_index in await _list_expired_contexts(cutoff):
        if active.get(session_id) == context_index:
            # 会话仍在内存中：下一次写库会把它重新写回来，跳过
            continue
        try:
            path = await archive_context(session_id, context_index)
        except Exception as e:
            logger.exception(f"[ContextArchive] 归档 {session_id} 的 context {context_index} 失败: {e}")
            result.failed.append((session_id, context_index))
            continue
        if path is not None:
            result.archived.append((session_id, context_index))
            logger.info(f"[ContextArchive] 已归档 {session_id} 的 context {context_index} -> {path}")
    return result
