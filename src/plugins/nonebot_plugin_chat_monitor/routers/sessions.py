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

"""会话相关的 REST API 路由"""

import base64
from typing import Any

from fastapi import APIRouter, Query
from fastapi.exceptions import HTTPException
from nonebot.log import logger

from ..auth import verify_admin, now_iso
from ..helpers import get_session_state, get_session_last_activity, serialize_cached_message

router = APIRouter(tags=["sessions"])


async def build_status() -> dict[str, Any]:
    """收集前端需要的全量状态数据（供广播和 /status 端点使用）。"""
    # 延迟导入避免循环依赖
    from nonebot_plugin_chat.core.ego.moonlark_main import moonlark_main
    from nonebot_plugin_chat.core.session import groups
    from nonebot_plugin_chat.enums import MoodEnum
    from nonebot_plugin_chat.utils.status_manager import get_status_manager

    status_mgr = get_status_manager()
    mood, mood_reason = status_mgr.get_status()
    mood_retention = status_mgr.get_mood_retention()

    from ..ws_manager import ws_manager

    sessions = []
    for session_id, session in groups.items():
        session_name = "?"
        try:
            name = await session.get_session_name()
            session_name = name or session_id
        except Exception:
            session_name = session_id
        sessions.append(
            {
                "id": session_id,
                "type": session.get_session_type() if hasattr(session, "get_session_type") else "unknown",
                "name": session_name,
                "state": get_session_state(session),
                "last_activity": get_session_last_activity(session),
                "message_count": len(session.cached_messages),
            }
        )

    ego_state = {}
    try:
        ego_state = moonlark_main._collect_state()
    except Exception:
        pass

    return {
        "type": "status_update",
        "server_time": now_iso(),
        "mood": {
            "emotion": mood.value,
            "intensity": mood_retention,
            "reason": mood_reason or "",
        },
        "ego": ego_state,
        "sessions": sessions,
        "ws_connections": ws_manager.count,
    }


@router.get("/chat-monitor/status")
async def get_status(token: str, salt: str):
    """获取 Moonlark 总体状态"""
    await verify_admin(token, salt)
    return await build_status()


@router.get("/chat-monitor/sessions")
async def list_sessions(token: str, salt: str):
    """列出所有活动会话"""
    await verify_admin(token, salt)
    from nonebot_plugin_chat.core.session import groups

    result = []
    for session_id, session in groups.items():
        session_name = "?"
        try:
            name = await session.get_session_name()
            session_name = name or session_id
        except Exception:
            session_name = session_id
        result.append(
            {
                "id": session_id,
                "type": session.get_session_type() if hasattr(session, "get_session_type") else "unknown",
                "name": session_name,
                "state": get_session_state(session),
                "last_activity": get_session_last_activity(session),
                "message_count": len(session.cached_messages),
                "tool_calls_count": len(session.tool_calls_history),
            }
        )
    return result


@router.get("/chat-monitor/sessions/{session_id}")
async def get_session_detail(session_id: str, token: str, salt: str):
    """获取单个会话详情"""
    await verify_admin(token, salt)
    from nonebot_plugin_chat.core.session import get_session_directly

    try:
        session = get_session_directly(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    session_name = "?"
    try:
        name = await session.get_session_name()
        session_name = name or session_id
    except Exception:
        session_name = session_id

    return {
        "id": session_id,
        "type": session.get_session_type() if hasattr(session, "get_session_type") else "unknown",
        "name": session_name,
        "state": get_session_state(session),
        "last_activity": get_session_last_activity(session),
        "message_count": len(session.cached_messages),
        "tool_calls_count": len(session.tool_calls_history),
        "ghot_coefficient": getattr(session, "ghot_coefficient", 1),
        "accumulated_text_length": getattr(session, "accumulated_text_length", 0),
        "last_interest": getattr(session, "last_interest", None),
        "queue_size": len(session.message_queue),
        "pending_interactions": len(getattr(session, "pending_interactions", {})),
    }


@router.get("/chat-monitor/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    token: str,
    salt: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """获取会话的缓存消息"""
    await verify_admin(token, salt)
    from nonebot_plugin_chat.core.session import get_session_directly

    try:
        session = get_session_directly(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = session.cached_messages
    total = len(messages)
    page = messages[-limit - offset :][:limit] if limit > 0 else messages
    return {
        "total": total,
        "messages": [serialize_cached_message(m) for m in page],
    }


@router.get("/chat-monitor/sessions/{session_id}/queue")
async def get_session_queue(session_id: str, token: str, salt: str):
    """获取会话的待处理消息队列（简要信息）"""
    await verify_admin(token, salt)
    from nonebot_plugin_chat.core.session import get_session_directly

    try:
        session = get_session_directly(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    items = []
    for item in session.message_queue:
        if item[0] == "message":
            _, details = item
            items.append(
                {
                    "type": "message",
                    "user_id": details[3],
                    "nickname": details[4],
                    "time": details[5].isoformat(),
                }
            )
        elif item[0] == "event":
            _, details = item
            items.append(
                {
                    "type": "event",
                    "prompt": details[0][:200],
                    "trigger_mode": details[1],
                }
            )
    return items


@router.get("/chat-monitor/sessions/{session_id}/tool-calls")
async def get_session_tool_calls(session_id: str, token: str, salt: str):
    """获取会话的工具调用历史"""
    await verify_admin(token, salt)
    from nonebot_plugin_chat.core.session import get_session_directly

    try:
        session = get_session_directly(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    return session.tool_calls_history


@router.get("/chat-monitor/sessions/{session_id}/openai-messages")
async def get_session_openai_messages(session_id: str, token: str, salt: str):
    """获取会话的 OpenAI 消息队列（当前上下文）"""
    await verify_admin(token, salt)
    from nonebot_plugin_chat.core.session import get_session_directly

    try:
        session = get_session_directly(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = session.processor.openai_messages.messages
    serialized = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls")
            serialized.append(
                {
                    "role": role,
                    "content": str(content)[:2000] if content else None,
                    "tool_calls": tool_calls,
                }
            )
        else:
            serialized.append(
                {
                    "role": getattr(msg, "role", "unknown"),
                    "content": str(getattr(msg, "content", ""))[:2000] if getattr(msg, "content", None) else None,
                    "tool_calls": getattr(msg, "tool_calls", None),
                }
            )
    return {"messages": serialized, "count": len(serialized)}


@router.get("/chat-monitor/sessions/{session_id}/messages/{msg_index}")
async def get_message_detail(
    session_id: str,
    msg_index: int,
    token: str,
    salt: str,
    include_images: bool = Query(False),
):
    """获取单条消息详情，可选择是否包含图片。"""
    await verify_admin(token, salt)
    from nonebot_plugin_chat.core.session import get_session_directly

    try:
        session = get_session_directly(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    if msg_index < 0 or msg_index >= len(session.cached_messages):
        raise HTTPException(status_code=404, detail="Message not found")

    msg = session.cached_messages[msg_index]
    result = serialize_cached_message(msg)
    if include_images and msg.get("images"):
        result["images"] = [base64.b64encode(img).decode("utf-8") for img in msg["images"]]
    return result
