"""EGO 相关的 REST API 路由（重写版）"""

from fastapi import APIRouter, Query, Request
from fastapi.exceptions import HTTPException
from nonebot_plugin_orm import get_session
from sqlalchemy import func, select

from ..auth import verify_admin_request

router = APIRouter(tags=["ego"])


@router.get("/chat-monitor/ego/status")
async def get_ego_status(request: Request):
    """获取 EGO 模块的详细状态"""
    await verify_admin_request(request)
    from nonebot_plugin_chat.core.ego.moonlark_main import moonlark_main
    from nonebot_plugin_chat.utils.status_manager import get_status_manager

    mood_intensity = get_status_manager().get_mood_retention()
    state = moonlark_main._collect_state()
    sleep_controller = moonlark_main.sleep_controller

    return {
        "sleep_mode": moonlark_main.state["sleep_mode"],
        "tiredness": getattr(sleep_controller, "tiredness", 0),
        "sleep_begin_time": getattr(sleep_controller, "sleep_begin_time", None),
        "mood_retention": mood_intensity,
        "mood": state.get("mood", {}),
        "blog_status": state.get("blog_status", {}),
        "plan": moonlark_main.planner.get_plan_text(),
    }


@router.get("/chat-monitor/ego/events")
async def list_ego_events(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """列出 EGO 的智能体事件记录"""
    await verify_admin_request(request)
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
async def get_ego_event(event_id: int, request: Request):
    """获取单条 EGO 事件详情"""
    await verify_admin_request(request)
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
