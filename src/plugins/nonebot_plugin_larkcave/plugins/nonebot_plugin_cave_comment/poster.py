from datetime import datetime
from .model import CommentData
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy.sql import func
from sqlalchemy import select

async def get_comment_id(session: async_scoped_session) -> int:
    result = await session.scalar(select(func.max(CommentData.id)))
    return (result + 1) if result is not None else 0

async def post(user_id: str, session: async_scoped_session, content: str, belong: int) -> int:
    comment_id = await get_comment_id(session)
    session.add(CommentData(
        id=comment_id,
        author=user_id,
        content=content,
        time=datetime.now(),
        belong=belong
    ))
    await session.commit()
    return comment_id
