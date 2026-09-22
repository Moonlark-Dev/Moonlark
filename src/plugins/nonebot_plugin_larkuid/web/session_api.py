"""会话生命周期接口：登出、设备管理。

- POST /api/logout：删除当前会话（真正的服务端登出，旧版只清浏览器凭据）；
- GET /api/sessions：列出当前用户的全部活跃会话（设备管理）；
- DELETE /api/sessions/{session_id}：踢掉指定会话，仅允许操作本人的会话。
"""

from datetime import datetime, timezone
from typing import Optional, cast

from fastapi import FastAPI, HTTPException, Request, status
from nonebot import get_app
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..models import SessionData
from ..session import AuthContext, get_current_session
from ..types import MessageResponse, SessionInfo

app = cast(FastAPI, get_app())


def _utc_epoch(value: Optional[datetime]) -> Optional[float]:
    """UTC naive -> epoch 秒；None 原样返回。"""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).timestamp()


@app.get("/api/sessions")
async def list_sessions(request: Request, current: AuthContext = get_current_session()) -> list[SessionInfo]:
    async with get_session() as session:
        rows = (
            await session.scalars(
                # MySQL 不支持 NULLS LAST，用布尔表达式把无创建时间的存量行排在最后
                select(SessionData)
                .where(SessionData.user_id == current.user_id)
                .order_by(SessionData.created_at.is_(None), SessionData.created_at.desc())
            )
        ).all()
        return [
            SessionInfo(
                session_id=row.session_id,
                current=row.session_id == current.session_id,
                device=row.device,
                created_at=_utc_epoch(row.created_at),
                last_active_at=_utc_epoch(row.last_active_at),
                expires_at=_utc_epoch(row.expiration_time),
            )
            for row in rows
        ]


@app.delete("/api/sessions/{session_id}")
async def remove_session(session_id: str, current: AuthContext = get_current_session()) -> MessageResponse:
    async with get_session() as session:
        data = await session.get(SessionData, session_id)
        if data is None or data.user_id != current.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await session.delete(data)
        await session.commit()
    return {"success": True, "message": "会话已移除"}


@app.post("/api/logout")
async def logout(current: AuthContext = get_current_session()) -> MessageResponse:
    async with get_session() as session:
        data = await session.get(SessionData, current.session_id)
        if data is not None:
            await session.delete(data)
            await session.commit()
    return {"success": True, "message": "已登出"}
