from nonebot_plugin_orm import get_scoped_session
from sqlalchemy import select

from ..models import EmailUser


async def mark_email_read(email_id: int, user_id: str) -> int:
    session = get_scoped_session()
    data = await session.scalar(select(EmailUser).where(EmailUser.user_id == user_id, EmailUser.email_id == email_id))
    if data is not None:
        data.is_read = True
        await session.commit()
    return email_id
