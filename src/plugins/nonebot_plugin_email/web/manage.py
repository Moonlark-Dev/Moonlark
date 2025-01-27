from typing import Any, AsyncGenerator
from fastapi import HTTPException, Request, status
from nonebot import get_app
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .get import get_email

from ..config import config
from ..models import EmailData
from ..config import config
from ..lang import lang
from nonebot_plugin_larkuid.session import get_user_id


async def get_email_list(user_id: str) -> AsyncGenerator[dict[str, Any], None]:
    async with get_session() as session:
        result = await session.scalars(select(EmailData.email_id))
    for email_id in result:
        yield await get_email(user_id, email_id)


@get_app().get("/api/emails")
async def _(request: Request, offset: int = 0, limit: int = 20, user_id: str = get_user_id()) -> dict:
    if user_id not in config.superusers:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    emails = [email async for email in get_email_list(user_id)]
    return {"total": len(emails), "emails": emails[offset : offset + limit]}
