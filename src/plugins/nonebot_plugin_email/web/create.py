from pathlib import Path
from fastapi import HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from nonebot import get_app
from nonebot_plugin_htmlrender import template_to_html



from ..utils.send import send_email, send_global_email
from ..utils.web_items import parse_items
from ..config import config
from ..lang import lang
from ...nonebot_plugin_larkuid.session import get_user_id_forcibly


@get_app().get("/admin/email/create")
async def _(request: Request, user_id: str = get_user_id_forcibly()) -> PlainTextResponse:
    if user_id not in config.superusers:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    html = await template_to_html(
        Path(__file__).parent.parent.joinpath("templates").as_posix(),
        "create.html.jinja",
        title=await lang.text("create.title", user_id),
        subject=await lang.text("create.subject", user_id),
        content=await lang.text("create.content", user_id),
        subject_input=await lang.text("create.subject_input", user_id),
        content_input=await lang.text("create.content_input", user_id),
        submit=await lang.text("create.submit", user_id),
        receiver=await lang.text("create.receiver", user_id),
        receiver_input=await lang.text("create.receiver_input", user_id),
        receiver_help=await lang.text("create.receiver_help", user_id),
        sender=await lang.text("create.sender", user_id),
        sender_input=await lang.text("create.sender_input", user_id),
        items=await lang.text("create.items", user_id),
        items_help=await lang.text("create.items_help", user_id),
    )
    return PlainTextResponse(html, media_type="text/html")


@get_app().get("/api/create_email")
async def _(
    request: Request,
    subject: str,
    content: str,
    receivers: str,
    sender: str,
    items: str,
    user_id: str = get_user_id_forcibly()
) -> int:
    if user_id not in config.superusers:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    if receivers == "all":
        return await send_global_email(
            subject,
            content,
            sender,
            parse_items(items)
        )
    else:
        return await send_email(
            receivers.split("|"),
            subject,
            content,
            sender,
            parse_items(items)
        )
