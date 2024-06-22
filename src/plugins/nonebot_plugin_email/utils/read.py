from nonebot_plugin_orm import get_scoped_session, get_session
from sqlalchemy import select

from .data import get_email_data

from ..models import EmailItem, EmailUser


async def has_item(email_id: int, user_id: str) -> bool:
    data = await get_email_data(email_id, user_id)
    return bool(data["items"])


async def mark_email_read(email_id: int, user_id: str, force: bool = False) -> int:
    session = get_scoped_session()
    data = await session.scalar(select(EmailUser).where(EmailUser.user_id == user_id, EmailUser.email_id == email_id))
    if data is not None and (await has_item(email_id, user_id) or force):
        data.is_read = True
        await session.commit()
    await session.close()
    return email_id
