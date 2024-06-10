from pathlib import Path
from typing import AsyncGenerator
from fastapi import HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from nonebot import get_app
from nonebot_plugin_htmlrender import template_to_html
from nonebot_plugin_orm import get_session
from sqlalchemy import select


from ..utils.data import get_email_data
from ..config import config
from ..models import Email, EmailUser
from ..config import config
from ..lang import lang
from ...nonebot_plugin_larkuid.session import get_user_id_forcibly


async def get_email_list(user_id: str) -> AsyncGenerator[dict[str, str], None]:
    async with get_session() as session:
        result = await session.scalars(select(Email.id))
    for email_id in result:
        email = await get_email_data(email_id, user_id)
        receivers = (await session.scalars(select(EmailUser.user_id).where(EmailUser.email_id == email_id))).all()
        receiver_count = await lang.text("multi_receiver", user_id, len(receivers))
        yield {
            "id": str(email["id"]),
            "subject": email["subject"],
            "time": email["time"].strftime("%Y-%m-%d %H:%M:%S"),
            "author": email["author"],
            "receivers": receivers[0] if len(receivers) == 1 else receiver_count,
            "items": str(len(email["items"]))
        }
    


@get_app().get("/admin/email/manage")
async def _(request: Request, page: int = 1, user_id: str = get_user_id_forcibly()) -> PlainTextResponse:
    if user_id not in config.superusers:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    emails = [item async for item in get_email_list(user_id)]
    html = await template_to_html(
        Path(__file__).parent.parent.joinpath("templates").as_posix(),
        "manage.html.jinja",
        title=await lang.text("manage.title", user_id),
        thead={
            "id": await lang.text("manage.thead_id", user_id),
            "subject": await lang.text("manage.thead_subject", user_id),
            "sender": await lang.text("manage.thead_sender", user_id),
            "time": await lang.text("manage.thead_time", user_id),
            "receivers": await lang.text("manage.thead_receivers", user_id),
            "control": await lang.text("manage.thead_control", user_id),
            "items": await lang.text("manage.thead_item", user_id)
        },
        action={
            "edit": await lang.text("manage.action_edit", user_id),
            "remove": await lang.text("manage.action_remove", user_id),
        },
        page_list_text=await lang.text("manage.page_list", user_id),
        info=await lang.text(
            "manage.info",
            user_id,
            count := len(emails),
            offset := (page - 1) * config.email_manage_page_size,
            end := page * config.email_manage_page_size,
            page,
            page_count := count // config.email_manage_page_size + 1
        ),
        emails=emails[offset:end],
        page_list=[i+1 for i in range(page_count)]
    )
    return PlainTextResponse(html, media_type="text/html")

