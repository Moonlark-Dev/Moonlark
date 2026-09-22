from typing import Literal

from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select

from nonebot_plugin_larkutils.user import get_user_id

from ..__main__ import email
from ..lang import lang
from ..models import EmailUser


@email.assign("read.email_id")
async def _(session: async_scoped_session, email_id: int | Literal["all"], user_id: str = get_user_id()) -> None:
    """将指定邮件（或全部邮件）标为已读"""
    count = 0
    for email_data in await session.scalars(select(EmailUser).where(EmailUser.user_id == user_id)):
        if email_data.email_id == email_id or email_id == "all":
            if not email_data.is_read:
                email_data.is_read = True
                count += 1
    await session.commit()
    await lang.finish("read.done", user_id, count)
