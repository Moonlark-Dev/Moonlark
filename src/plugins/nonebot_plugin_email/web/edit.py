from typing import Optional
from fastapi import HTTPException, Request, status
from nonebot import get_app
from nonebot_plugin_orm import get_scoped_session

from ..models import EmailEditArgs
from ..models import Email
from ..config import config
from ...nonebot_plugin_larkuid.session import get_user_id


@get_app().put("/api/emails/{email_id}/edit", status_code=status.HTTP_204_NO_CONTENT)
async def _(request: Request, email_id: int, args: EmailEditArgs, user_id: str = get_user_id()) -> None:
    if user_id not in config.superusers:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    session = get_scoped_session()
    email = await session.get(Email, email_id)
    if email is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    email.content = args.content or email.content
    email.subject = args.subject or email.subject
    await session.commit()
    await session.close()
