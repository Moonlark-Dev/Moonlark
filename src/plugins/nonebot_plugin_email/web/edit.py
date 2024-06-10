from pathlib import Path
from typing import AsyncGenerator
from fastapi import HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from nonebot import get_app
from nonebot_plugin_htmlrender import template_to_html
from nonebot_plugin_orm import get_scoped_session, get_session
from sqlalchemy import select


from ..utils.data import get_email_data
from ..config import config
from ..models import Email, EmailUser
from ..config import config
from ..lang import lang
from ...nonebot_plugin_larkuid.session import get_user_id_forcibly


@get_app().get("/api/set_email_content", status_code=status.HTTP_204_NO_CONTENT)
async def _(request: Request, email_id: int, subject: str, content: str, user_id: str = get_user_id_forcibly()) -> None:
    if user_id not in config.superusers:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    session = get_scoped_session()
    email = await session.get(Email, email_id)
    if email is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    email.content = content
    email.subject = subject
    await session.commit()
    await session.close()


@get_app().get("/admin/email/{email_id}/edit")
async def _(request: Request, email_id: int, user_id: str = get_user_id_forcibly()) -> PlainTextResponse:
    if user_id not in config.superusers:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    session = get_scoped_session()
    email = await session.get(Email, email_id)
    if email is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    html = await template_to_html(
        Path(__file__).parent.parent.joinpath("templates").as_posix(),
        "edit.html.jinja",
        title=await lang.text("edit.title", user_id),
        id=await lang.text("edit.id", user_id),
        subject=await lang.text("edit.subject", user_id),
        content=await lang.text("edit.content", user_id),
        submit=await lang.text("edit.submit", user_id),
        email_id=email.id,
        origin_content=email.content,
        origin_subject=email.subject
    )
    await session.close()
    return PlainTextResponse(html, media_type="text/html")
