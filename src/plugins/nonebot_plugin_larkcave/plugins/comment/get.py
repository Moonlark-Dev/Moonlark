from typing import Optional
from nonebot_plugin_alconna import UniMessage
from .models import CommentData
from nonebot_plugin_orm import AsyncSession, async_scoped_session
from sqlalchemy import select
from .image import generate


async def get_comment_list(belong: int, session: async_scoped_session | AsyncSession) -> list[CommentData]:
    return list((await session.scalars(select(CommentData).where(CommentData.belong == belong))).all())


async def get_comments(cave_id: int, session: async_scoped_session, user_id: str) -> Optional[UniMessage]:
    if not (comment_list := await get_comment_list(cave_id, session)):
        return
    return UniMessage().image(raw=await generate(comment_list, cave_id, user_id))
