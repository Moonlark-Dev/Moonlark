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

"""笔记相关的 REST API 路由"""

from datetime import datetime

from fastapi import APIRouter, Query, Request
from fastapi.exceptions import HTTPException
from nonebot_plugin_orm import get_session
from sqlalchemy import func, select

from ..auth import verify_admin

router = APIRouter(tags=["notes"])


@router.get("/chat-monitor/notes")
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
    from nonebot_plugin_chat.models import Note

    async with get_session() as db_session:
        query = select(Note)
        if context_id:
            query = query.where(Note.context_id == context_id)
        if search:
            query = query.where(Note.content.like(f"%{search}%"))
        query = query.order_by(Note.created_time.desc()).offset(offset).limit(limit)
        result = await db_session.scalars(query)
        notes = result.all()

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


@router.post("/chat-monitor/notes")
async def create_note(request: Request, token: str, salt: str):
    """创建新笔记"""
    await verify_admin(token, salt)
    from nonebot_plugin_chat.models import Note

    body = await request.json()
    context_id = body.get("context_id", "chat-monitor")
    content = body.get("content", "")
    keywords = body.get("keywords", "")
    expire_hours = body.get("expire_hours")

    if not content:
        raise HTTPException(status_code=400, detail="Content is required")

    now = datetime.now()
    note = Note(
        context_id=context_id,
        content=content,
        keywords=keywords,
        created_time=now.timestamp(),
        expire_time=(
            datetime.fromtimestamp(now.timestamp() + expire_hours * 3600) if expire_hours and expire_hours > 0 else None
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


@router.put("/chat-monitor/notes/{note_id}")
async def update_note(note_id: int, request: Request, token: str, salt: str):
    """更新笔记"""
    await verify_admin(token, salt)
    from nonebot_plugin_chat.models import Note

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
            note.expire_time = datetime.fromtimestamp(datetime.now().timestamp() + h * 3600) if h and h > 0 else None
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


@router.delete("/chat-monitor/notes/{note_id}")
async def delete_note(note_id: int, token: str, salt: str):
    """删除笔记"""
    await verify_admin(token, salt)
    from nonebot_plugin_chat.models import Note

    async with get_session() as db_session:
        note = await db_session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        await db_session.delete(note)
        await db_session.commit()
    return {"deleted": True, "id": note_id}
