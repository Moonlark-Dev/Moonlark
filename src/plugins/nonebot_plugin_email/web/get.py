from fastapi import HTTPException, Request, status
from sqlalchemy.exc import NoResultFound
from nonebot import get_app

from nonebot_plugin_larkuid.session import get_user_id

from ..config import config
from ..models import EmailUser
from ..utils.data import get_email_data


from nonebot_plugin_orm import get_session
from sqlalchemy import select


from typing import Any


async def get_email(user_id: str, email_id: int) -> dict[str, Any]:
    async with get_session() as session:
        email = await get_email_data(email_id, user_id)
        receivers = (await session.scalars(select(EmailUser.user_id).where(EmailUser.email_id == email_id))).all()
        return {
            "id": email["id"],
            "subject": email["subject"],
            "time": email["time"],
            "author": email["author"],
            "receivers": receivers,
            "items": email["items"],
        }


@get_app().get("/api/emails/{email_id}")
async def _(request: Request, email_id: int, user_id: str = get_user_id()) -> dict:
    if user_id not in config.superusers:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    try:
        return await get_email(user_id, email_id)
    except NoResultFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
