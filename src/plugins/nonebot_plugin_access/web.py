from fastapi import Request
from nonebot import get_app
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..nonebot_plugin_larkuid.session import get_user_id
from .models import SubjectData


@get_app().get("/api/users/me/permissions")
async def _(_request: Request, user_id: str = get_user_id()) -> dict[str, bool]:
    perms = {}
    async with get_session() as session:
        for item in await session.scalars(select(SubjectData).where(SubjectData.subject == user_id)):
            perms[item.name] = item.available
    return perms
