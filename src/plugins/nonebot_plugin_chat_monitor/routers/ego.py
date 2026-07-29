"""EGO 相关的 REST API 路由（重写版）"""

from datetime import datetime

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


@router.get("/chat-monitor/ego/plan")
async def get_ego_plan(request: Request):
    """获取今日计划详情（时间段+内容列表）"""
    await verify_admin_request(request)
    from nonebot_plugin_chat.core.ego.moonlark_main import moonlark_main

    plan_items = moonlark_main.planner.get_plan()
    if not plan_items:
        return {"items": []}

    return {
        "items": [
            {
                "period": item.period,
                "content": item.content,
            }
            for item in plan_items
        ],
    }


@router.get("/chat-monitor/ego/session-events")
async def get_session_events(request: Request, date: str = Query(default="")):
    """获取 EventCollector 收集的会话事件摘要"""
    await verify_admin_request(request)
    from nonebot_plugin_chat.core.ego.event_collector import event_collector

    target_date = date if date else datetime.now().strftime("%Y-%m-%d")
    summary = await event_collector.get_all_events_summary(date=target_date)
    return {"date": target_date, "summary": summary}


@router.get("/chat-monitor/ego/diaries")
async def list_ego_diaries(
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """列出日记记录（替代废弃的 AgentEvent）"""
    await verify_admin_request(request)
    from nonebot_plugin_chat.models import DiaryPost

    async with get_session() as db_session:
        count_query = select(func.count()).select_from(DiaryPost)
        total = (await db_session.scalar(count_query)) or 0

        query = (
            select(DiaryPost)
            .order_by(DiaryPost.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db_session.scalars(query)
        diaries = result.all()

    return {
        "total": total,
        "diaries": [
            {
                "id": d.id,
                "content": d.content[:500],
                "keywords": d.keywords,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "expire_at": d.expire_at.isoformat() if d.expire_at else None,
            }
            for d in diaries
        ],
    }


@router.get("/chat-monitor/ego/blogs")
async def list_ego_blogs(
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """列出博客记录"""
    await verify_admin_request(request)
    from nonebot_plugin_chat.models import BlogPost

    async with get_session() as db_session:
        count_query = select(func.count()).select_from(BlogPost)
        total = (await db_session.scalar(count_query)) or 0

        query = (
            select(BlogPost)
            .order_by(BlogPost.create_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db_session.scalars(query)
        blogs = result.all()

    return {
        "total": total,
        "blogs": [
            {
                "id": b.id,
                "title": b.title,
                "content": b.content[:300],
                "created_at": b.create_at.isoformat() if b.create_at else None,
            }
            for b in blogs
        ],
    }


@router.get("/chat-monitor/ego/events")
async def list_ego_events(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """列出 EGO 的智能体事件记录（废弃中，保留兼容）"""
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
    """获取单条 EGO 事件详情（废弃中，保留兼容）"""
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
