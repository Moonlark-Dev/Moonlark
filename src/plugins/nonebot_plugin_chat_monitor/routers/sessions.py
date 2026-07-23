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

from fastapi import APIRouter, Query, Request
from fastapi.exceptions import HTTPException
from nonebot.log import logger

from ..auth import verify_admin_request, now_iso
from ..helpers import (
    get_cached_session_name,
    get_session_state,
    get_session_last_activity,
    serialize_cached_message,
)

router = APIRouter(tags=["sessions"])


async def build_status() -> dict[str, Any]:
    """收集前端需要的全量状态数据（供广播和 /status 端点使用）。"""
    from nonebot_plugin_chat.core.ego.moonlark_main import moonlark_main
    from nonebot_plugin_chat.core.session import groups
    from nonebot_plugin_chat.utils.status_manager import get_status_manager

    status_mgr = get_status_manager()
    mood, mood_reason = status_mgr.get_status()
    mood_retention = status_mgr.get_mood_retention()

    from ..ws_manager import ws_manager

    sessions = []
    for session_id, session in groups.items():
        session_name = await get_cached_session_name(session, session_id)
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
    except Exception as exc:
        logger.debug(f"[ChatMonitor] 收集 EGO 状态失败: {exc}")

    return {
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
async def get_status(request: Request):
    """获取 Moonlark 总体状态"""
    await verify_admin_request(request)
    return await build_status()


@router.get("/chat-monitor/sessions")
async def list_sessions(request: Request):
    """列出所有活动会话"""
    await verify_admin_request(request)
    from nonebot_plugin_chat.core.session import groups

    result = []
    for session_id, session in groups.items():
        session_name = await get_cached_session_name(session, session_id)
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
async def get_session_detail(session_id: str, request: Request):
    """获取单个会话详情"""
    await verify_admin_request(request)
    from nonebot_plugin_chat.core.session import get_session_directly

    try:
        session = get_session_directly(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    session_name = await get_cached_session_name(session, session_id)

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
        "last_thought": getattr(session.processor.openai_messages, "last_thought", None),
    }


@router.get("/chat-monitor/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """获取会话的缓存消息"""
    await verify_admin_request(request)
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
async def get_session_queue(session_id: str, request: Request):
    """获取会话的待处理消息队列（简要信息）"""
    await verify_admin_request(request)
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
async def get_session_tool_calls(session_id: str, request: Request):
    """获取会话的工具调用历史"""
    await verify_admin_request(request)
    from nonebot_plugin_chat.core.session import get_session_directly

    try:
        session = get_session_directly(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    return session.tool_calls_history


@router.get("/chat-monitor/sessions/{session_id}/openai-messages")
async def get_session_openai_messages(session_id: str, request: Request):
    """获取会话的 OpenAI 消息队列（当前上下文）"""
    await verify_admin_request(request)
    from nonebot_plugin_chat.core.session import get_session_directly

    try:
        session = get_session_directly(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = session.processor.openai_messages.messages
    serialized = []
    for msg in messages:
        if isinstance(msg, dict):
            serialized.append(
                {
                    "role": msg.get("role", "unknown"),
                    "content": str(msg.get("content", ""))[:2000] if msg.get("content") else None,
                    "tool_calls": msg.get("tool_calls"),
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
    # 将最近一次 OpenAI API 响应体序列化
    fetcher = session.processor.openai_messages.fetcher
    if fetcher is not None and hasattr(fetcher, "last_response") and fetcher.last_response is not None:
        last_response_raw = fetcher.last_response.model_dump(mode="json")
    else:
        last_response_raw = None

    return {"messages": serialized, "count": len(serialized), "last_response": last_response_raw}


@router.get("/chat-monitor/sessions/{session_id}/messages/{msg_index}")
async def get_message_detail(
    session_id: str,
    msg_index: int,
    request: Request,
    include_images: bool = Query(False),
):
    """获取单条消息详情，可选择是否包含图片。"""
    await verify_admin_request(request)
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


@router.get("/chat-monitor/sessions/{session_id}/messages/{msg_index}/context")
async def get_message_context(session_id: str, msg_index: int, request: Request):
    """获取消息的完整上下文格式（与 AI 上下文中插入的格式相同）。"""
    await verify_admin_request(request)
    from nonebot_plugin_chat.core.session import get_session_directly

    try:
        session = get_session_directly(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    if msg_index < 0 or msg_index >= len(session.cached_messages):
        raise HTTPException(status_code=404, detail="Message not found")

    msg = session.cached_messages[msg_index]

    # 格式化消息文本
    try:
        from nonebot_plugin_chat.utils.message import generate_message_string
        formatted_msg = generate_message_string(msg)
    except ImportError:
        formatted_msg = f"[{msg.get('nickname', '?')}]({msg.get('message_id', '?')}): {msg.get('content', '')}\n"

    # 搜集额外上下文信息
    lines = [formatted_msg]

    # additional_info 块
    try:
        from nonebot_plugin_chat.utils.status_manager import get_status_manager

        status_manager = get_status_manager()

        # Token 信息
        token_info = ""
        if hasattr(session, 'processor') and hasattr(session.processor, 'token_bucket'):
            try:
                token_val = round(session.processor.token_bucket.get(), 2)
                token_info = f"当前 Token: {token_val}"
            except Exception:
                pass

        # 好感度（最近一条消息的发送者）
        affection = ""
        user_id = msg.get("user_id", "")
        if user_id and hasattr(session, 'processor') and hasattr(session.processor, 'affection_manager'):
            try:
                level = session.processor.affection_manager.get_affection_level(user_id)
                tag = session.processor.affection_manager.get_affection_tag(user_id)
                affection = f"{msg.get('nickname', '?')} 的好感度: {level}/{tag}"
            except Exception:
                pass

        # 最近活动
        recent_actions = ""
        try:
            from nonebot_plugin_chat.core.ego import moonlark_main
            actions = moonlark_main._get_recent_actions_text()
            if actions:
                recent_actions = f"最近做的事:\n{actions}"
        except Exception:
            pass

        # 笔记
        notes_text = ""
        try:
            from nonebot_plugin_chat.utils.note_manager import get_context_notes
            note_mgr = await get_context_notes(context_id=session_id)
            all_notes = await note_mgr.get_notes()
            if all_notes:
                from nonebot_plugin_chat.utils.note_manager import NoteSchema
                note_lines = []
                for n in all_notes:
                    if isinstance(n, NoteSchema):
                        from datetime import datetime
                        created = datetime.fromtimestamp(n.created_time).strftime("%m-%d")
                        note_lines.append(f"- {n.content}  (#{n.id}，创建于 {created})")
                    elif isinstance(n, dict):
                        note_lines.append(f"- {n.get('content', '')}")
                if note_lines:
                    notes_text = "笔记:\n" + "\n".join(note_lines[-10:])
        except Exception:
            pass

        # 当前状态
        mood_type, mood_reason = status_manager.get_status()
        mood_label = mood_type.value if hasattr(mood_type, 'value') else str(mood_type)
        state_text = f"心情：{mood_label} (情感强度: {status_manager.get_mood_retention()}; 原因: {mood_reason or '无'})"

        # 组装 additional_info
        info_parts = []
        now = now_iso()
        info_parts.append(f"<additional_info>\n当前时间: {now}")
        if token_info:
            info_parts.append(token_info)
        if affection:
            info_parts.append(affection)
        if notes_text:
            info_parts.append(notes_text)
        if recent_actions:
            info_parts.append(recent_actions)
        info_parts.append(state_text)
        info_parts.append("</additional_info>")

        lines.append("\n".join(info_parts))
    except Exception as e:
        logger.debug(f"[ChatMonitor] 构建消息上下文时出错: {e}")

    return {"context": "".join(lines)}

