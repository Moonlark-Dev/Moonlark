from typing import Literal
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select

from ..models import EmailUser
from ..lang import lang
from ...nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import email


@email.assign("unread.email_id")
async def _(session: async_scoped_session, email_id: int | Literal["all"], user_id: str = get_user_id()) -> None:
    count = 0
    for email in await session.scalars(select(EmailUser).where(EmailUser.user_id == user_id)):
        if email.email_id == email_id or email_id == "all":
            email.is_read = False
            count += 1
    await session.commit()
    await lang.finish("unread.done", user_id, count)
