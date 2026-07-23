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

"""EGO 相关的 REST API 路由"""

from fastapi import APIRouter, Query
from fastapi.exceptions import HTTPException
from nonebot_plugin_orm import get_session
from sqlalchemy import func, select

from ..auth import verify_admin

router = APIRouter(tags=["ego"])


@router.get("/chat-monitor/ego/status")
async def get_ego_status(token: str, salt: str):
    """获取 EGO 模块的详细状态"""
    await verify_admin(token, salt)
    from nonebot_plugin_chat.core.ego.moonlark_main import moonlark_main
    from nonebot_plugin_chat.utils.status_manager import get_status_manager

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


@router.get("/chat-monitor/ego/events")
async def list_ego_events(
    token: str,
    salt: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """列出 EGO 的智能体事件记录"""
    await verify_admin(token, salt)
    from nonebot_plugin_chat.models import AgentEvent

    async with get_session() as db_session:
        count_query = select(func.count()).select_from(AgentEvent)
        total = (await db_session.scalar(count_query)) or 0

        query = select(AgentEvent).order_by(AgentEvent.created_at.desc()).offset(offset).limit(limit)
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


@router.get("/chat-monitor/ego/events/{event_id}")
async def get_ego_event(event_id: int, token: str, salt: str):
    """获取单条 EGO 事件详情"""
    await verify_admin(token, salt)
    from nonebot_plugin_chat.models import AgentEvent

    async with get_session() as db_session:
        event = await db_session.get(AgentEvent, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        return {
            "id": event.id,
            "created_at": event.created_at.isoformat() if event.created_at else None,
            "content": event.content,
        }
