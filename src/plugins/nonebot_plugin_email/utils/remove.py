from nonebot_plugin_orm import get_scoped_session
from sqlalchemy import select

from ..models import Email, EmailItem, EmailUser


async def remove_email(email_id: int) -> None:
    session = get_scoped_session()
    await session.delete(await session.get_one(Email, email_id))
    for item in await session.scalars(select(EmailItem).where(EmailItem.belong == email_id)):
        await session.delete(item)
    for item in await session.scalars(select(EmailUser).where(EmailUser.email_id == email_id)):
        await session.delete(item)
    await session.commit()
