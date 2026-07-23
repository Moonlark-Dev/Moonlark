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
"""Chat Monitor - 为 Moonlark 提供 WebSocket 和 REST API 接口，用于实时监控聊天和 EGO 状态。"""

import asyncio
import hashlib
import json
from datetime import datetime
from typing import Any, Optional, cast
from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.exceptions import HTTPException
from nonebot import get_app, get_driver
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_chat.core.ego.moonlark_main import moonlark_main
from nonebot_plugin_chat.core.session import groups
from nonebot_plugin_chat.enums import MoodEnum
from nonebot_plugin_chat.models import AgentEvent, Note
from nonebot_plugin_chat.utils.status_manager import get_status_manager
from nonebot_plugin_orm import get_session
from sqlalchemy import func, select
from datetime import timezone

from .config import config

app: FastAPI = cast(FastAPI, get_app())

# ========================================================================
# 认证
# ========================================================================


async def verify_admin(token: str, salt: str) -> None:
    """验证 admin token，与 status_report 使用相同的方式。"""
    expected = hashlib.sha256(f"{config.status_report_password}+{salt}".encode()).hexdigest()
    if token != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid access token")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ========================================================================
# 辅助函数
# ========================================================================


def _get_session_state(session: Any) -> str:
    """获取会话的当前状态：parsing / replying / idle"""
    if session.processor.openai_messages.fetcher_lock.locked():
        return "replying"
    if session.message_queue:
        return "parsing"
    return "idle"


def _get_session_last_activity(session: Any) -> Optional[str]:
    """获取会话的最后活动时间"""
    if session.cached_messages:
        return session.cached_messages[-1]["send_time"].isoformat()
    return session.last_activate.isoformat() if hasattr(session, "last_activate") and session.last_activate else None


def _serialize_cached_message(msg: dict) -> dict:
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


# ========================================================================
# WebSocket 管理器
# ========================================================================


class ConnectionManager:
    """管理 WebSocket 连接，广播状态更新。"""

    def __init__(self):
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)
        logger.info(f"[ChatMonitor] WebSocket 客户端已连接，当前 {len(self._connections)} 个连接")

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)
        logger.info(f"[ChatMonitor] WebSocket 客户端已断开，当前 {len(self._connections)} 个连接")

    async def broadcast(self, data: dict):
        """向所有连接的客户端广播消息。"""
        async with self._lock:
            dead = []
            for ws in self._connections:
                try:
                    await ws.send_json(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._connections.remove(ws)


ws_manager = ConnectionManager()


# ========================================================================
# 定时广播（每 2 秒推送一次状态更新）
# ========================================================================


@get_driver().on_startup
async def _start_ws_broadcast():
    """在 NoneBot 启动后启动 WebSocket 广播循环。"""
    asyncio.create_task(_ws_broadcast_loop())


async def _ws_broadcast_loop():
    """每 2 秒收集并广播一次全量状态。"""
    await asyncio.sleep(3)  # 等待 NoneBot 完全初始化
    while True:
        try:
            if ws_manager._connections:
                payload = await _collect_full_status()
                await ws_manager.broadcast(payload)
        except Exception as e:
            logger.warning(f"[ChatMonitor] 广播异常: {e}")
        await asyncio.sleep(2)


async def _collect_full_status() -> dict:
    """收集前端需要的全量状态数据。"""
    status_mgr = get_status_manager()
    mood, mood_reason = status_mgr.get_status()
    mood_retention = status_mgr.get_mood_retention()

    # 服务器时间
    server_time = _now_iso()

    # 会话概览
    sessions = []
    for session_id, session in groups.items():
        session_name = "?"
        try:
            session_name = (await session.get_session_name()) or session_id
        except Exception:
            session_name = session_id
        sessions.append({
            "id": session_id,
            "type": session.get_session_type() if hasattr(session, "get_session_type") else "unknown",
            "name": session_name,
            "state": _get_session_state(session),
            "last_activity": _get_session_last_activity(session),
            "message_count": len(session.cached_messages),
        })

    # Moonlark EGO 状态
    ego_state = {}
    try:
        ego_state = moonlark_main._collect_state()
    except Exception:
        pass

    return {
        "type": "status_update",
        "server_time": server_time,
        "mood": {
            "emotion": mood.value,
            "intensity": mood_retention,
            "reason": mood_reason or "",
        },
        "ego": ego_state,
        "sessions": sessions,
        "ws_connections": len(ws_manager._connections),
    }


# ========================================================================
# REST API
# ========================================================================


@app.get("/chat-monitor/status")
async def get_status(token: str, salt: str):
    """获取 Moonlark 总体状态"""
    await verify_admin(token, salt)
    return await _collect_full_status()


@app.get("/chat-monitor/sessions")
async def list_sessions(token: str, salt: str):
    """列出所有活动会话"""
    await verify_admin(token, salt)
    result = []
    for session_id, session in groups.items():
        session_name = "?"
        try:
            session_name = (await session.get_session_name()) or session_id
        except Exception:
            session_name = session_id
        result.append({
            "id": session_id,
            "type": session.get_session_type() if hasattr(session, "get_session_type") else "unknown",
            "name": session_name,
            "state": _get_session_state(session),
            "last_activity": _get_session_last_activity(session),
            "message_count": len(session.cached_messages),
            "tool_calls_count": len(session.tool_calls_history),
        })
    return result


@app.get("/chat-monitor/sessions/{session_id}")
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
        session_name = (await session.get_session_name()) or session_id
    except Exception:
        session_name = session_id

    return {
        "id": session_id,
        "type": session.get_session_type() if hasattr(session, "get_session_type") else "unknown",
        "name": session_name,
        "state": _get_session_state(session),
        "last_activity": _get_session_last_activity(session),
        "message_count": len(session.cached_messages),
        "tool_calls_count": len(session.tool_calls_history),
        "ghot_coefficient": getattr(session, "ghot_coefficient", 1),
        "accumulated_text_length": getattr(session, "accumulated_text_length", 0),
        "last_interest": getattr(session, "last_interest", None),
        "queue_size": len(session.message_queue),
        "pending_interactions": len(getattr(session, "pending_interactions", {})),
    }


@app.get("/chat-monitor/sessions/{session_id}/messages")
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
    page = messages[-limit - offset:][:limit] if limit > 0 else messages
    return {
        "total": total,
        "messages": [_serialize_cached_message(m) for m in page],
    }


@app.get("/chat-monitor/sessions/{session_id}/queue")
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
            items.append({
                "type": "message",
                "user_id": details[3],
                "nickname": details[4],
                "time": details[5].isoformat(),
            })
        elif item[0] == "event":
            _, details = item
            items.append({
                "type": "event",
                "prompt": details[0][:200],
                "trigger_mode": details[1],
            })
    return items


@app.get("/chat-monitor/sessions/{session_id}/tool-calls")
async def get_session_tool_calls(session_id: str, token: str, salt: str):
    """获取会话的工具调用历史"""
    await verify_admin(token, salt)
    from nonebot_plugin_chat.core.session import get_session_directly

    try:
        session = get_session_directly(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    return session.tool_calls_history


@app.get("/chat-monitor/sessions/{session_id}/openai-messages")
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
            serialized.append({
                "role": role,
                "content": str(content)[:2000] if content else None,
                "tool_calls": tool_calls,
            })
        else:
            serialized.append({
                "role": getattr(msg, "role", "unknown"),
                "content": str(getattr(msg, "content", ""))[:2000] if getattr(msg, "content", None) else None,
                "tool_calls": getattr(msg, "tool_calls", None),
            })
    return {"messages": serialized, "count": len(serialized)}


# ========================================================================
# 笔记相关 API
# ========================================================================


@app.get("/chat-monitor/notes")
async def list_notes(
    token: str,
    salt: str,
    context_id: str = Query("", description="可选的会话/上下文 ID，为空则返回所有笔记"),
    search: str = Query("", description="搜索关键词（在内容中匹配）"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """列出笔记"""
    await verify_admin(token, salt)
    async with get_session() as db_session:
        query = select(Note)
        if context_id:
            query = query.where(Note.context_id == context_id)
        if search:
            query = query.where(Note.content.like(f"%{search}%"))
        query = query.order_by(Note.created_time.desc()).offset(offset).limit(limit)
        result = await db_session.scalars(query)
        notes = result.all()

        # 获取总数
        count_query = select(func.count()).select_from(Note)
        if context_id:
            count_query = count_query.where(Note.context_id == context_id)
        if search:
            count_query = count_query.where(Note.content.like(f"%{search}%"))
        total = (await db_session.scalar(count_query)) or 0

    return {
        "total": total,
        "notes": [
            {
                "id": n.id,
                "context_id": n.context_id,
                "content": n.content,
                "keywords": n.keywords,
                "created_time": n.created_time,
                "expire_time": n.expire_time.isoformat() if n.expire_time else None,
            }
            for n in notes
        ],
    }


@app.post("/chat-monitor/notes")
async def create_note(request: Request, token: str, salt: str):
    """创建新笔记"""
    await verify_admin(token, salt)
    body = await request.json()
    context_id = body.get("context_id", "chat-monitor")
    content = body.get("content", "")
    keywords = body.get("keywords", "")
    expire_hours = body.get("expire_hours")

    if not content:
        raise HTTPException(status_code=400, detail="Content is required")

    note = Note(
        context_id=context_id,
        content=content,
        keywords=keywords,
        created_time=datetime.now().timestamp(),
        expire_time=(
            datetime.fromtimestamp(datetime.now().timestamp() + expire_hours * 3600)
            if expire_hours and expire_hours > 0
            else None
        ),
    )
    async with get_session() as db_session:
        db_session.add(note)
        await db_session.commit()
        await db_session.refresh(note)

    return {
        "id": note.id,
        "context_id": note.context_id,
        "content": note.content,
        "keywords": note.keywords,
        "created_time": note.created_time,
        "expire_time": note.expire_time.isoformat() if note.expire_time else None,
    }


@app.put("/chat-monitor/notes/{note_id}")
async def update_note(note_id: int, request: Request, token: str, salt: str):
    """更新笔记"""
    await verify_admin(token, salt)
    body = await request.json()
    async with get_session() as db_session:
        note = await db_session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")

        if "content" in body:
            note.content = body["content"]
        if "keywords" in body:
            note.keywords = body["keywords"]
        if "expire_hours" in body:
            h = body["expire_hours"]
            note.expire_time = (
                datetime.fromtimestamp(datetime.now().timestamp() + h * 3600) if h and h > 0 else None
            )
        await db_session.commit()
        await db_session.refresh(note)

    return {
        "id": note.id,
        "context_id": note.context_id,
        "content": note.content,
        "keywords": note.keywords,
        "created_time": note.created_time,
        "expire_time": note.expire_time.isoformat() if note.expire_time else None,
    }


@app.delete("/chat-monitor/notes/{note_id}")
async def delete_note(note_id: int, token: str, salt: str):
    """删除笔记"""
    await verify_admin(token, salt)
    async with get_session() as db_session:
        note = await db_session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        await db_session.delete(note)
        await db_session.commit()
    return {"deleted": True, "id": note_id}


# ========================================================================
# EGO 相关 API
# ========================================================================


@app.get("/chat-monitor/ego/status")
async def get_ego_status(token: str, salt: str):
    """获取 EGO 模块的详细状态"""
    await verify_admin(token, salt)
    mood_intensity = get_status_manager().get_mood_retention()
    state = moonlark_main._collect_state()

    sleep_controller = moonlark_main.sleep_controller
    self_action = moonlark_main.self_action

    return {
        "sleep_mode": moonlark_main.state["sleep_mode"],
        "tiredness": getattr(sleep_controller, "tiredness", 0),
        "sleep_begin_time": getattr(sleep_controller, "sleep_begin_time", None),
        "current_activity": self_action.current_activity,
        "activity_start_time": self_action.activity_start_time.isoformat() if self_action.activity_start_time else None,
        "decision_history": moonlark_main.state["decision_history"],
        "last_decision_time": moonlark_main.state.get("last_decision_time"),
        "mood_retention": mood_intensity,
        "mood": state.get("mood", {}),
        "blog_status": state.get("blog_status", {}),
        "proactive_info": state.get("proactive_info", {}),
    }


@app.get("/chat-monitor/ego/events")
async def list_ego_events(
    token: str,
    salt: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """列出 EGO 的智能体事件记录"""
    await verify_admin(token, salt)
    async with get_session() as db_session:
        count_query = select(func.count()).select_from(AgentEvent)
        total = (await db_session.scalar(count_query)) or 0

        query = (
            select(AgentEvent)
            .order_by(AgentEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db_session.scalars(query)
        events = result.all()

    return {
        "total": total,
        "events": [
            {
                "id": e.id,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "content": e.content,
            }
            for e in events
        ],
    }


@app.get("/chat-monitor/ego/events/{event_id}")
async def get_ego_event(event_id: int, token: str, salt: str):
    """获取单条 EGO 事件详情"""
    await verify_admin(token, salt)
    async with get_session() as db_session:
        event = await db_session.get(AgentEvent, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        return {
            "id": event.id,
            "created_at": event.created_at.isoformat() if event.created_at else None,
            "content": event.content,
        }


# ========================================================================
# WebSocket 端点
# ========================================================================


@app.websocket("/chat-monitor/ws")
async def chat_monitor_websocket(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
    salt = websocket.query_params.get("salt", "")

    # 验证 token
    expected = hashlib.sha256(f"{config.status_report_password}+{salt}".encode()).hexdigest()
    if token != expected:
        await websocket.close(code=4001, reason="Invalid access token")
        return

    await ws_manager.connect(websocket)
    try:
        # 发送初始全量状态
        initial = await _collect_full_status()
        await websocket.send_json(initial)
        # 保持连接，广播由 _ws_broadcast_loop 负责
        while True:
            # 等待客户端消息（ping/pong 保活）
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except (json.JSONDecodeError, Exception):
                pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[ChatMonitor] WebSocket 异常: {e}")
    finally:
        await ws_manager.disconnect(websocket)


# ========================================================================
# 定时清理过期连接
# ========================================================================


@scheduler.scheduled_job("interval", minutes=5, id="chat_monitor_cleanup")
async def _cleanup_websocket_connections():
    """定期清理已断开的 WebSocket 连接（备用清理）。"""
    # WebSocket 断开时 FastAPI 会抛 WebSocketDisconnect，
    # 我们的 disconnect() 会处理移除。此函数作为额外的安全清理。
    pass


# ========================================================================
# 辅助：用于获取缓存消息中的图片（二进制图片单独接口）
# ========================================================================


@app.get("/chat-monitor/sessions/{session_id}/messages/{msg_index}")
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
    result = _serialize_cached_message(msg)
    if include_images and msg.get("images"):
        import base64

        result["images"] = [base64.b64encode(img).decode("utf-8") for img in msg["images"]]
    return result
