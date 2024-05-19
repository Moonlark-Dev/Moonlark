from pathlib import Path
from fastapi import Request
from fastapi.responses import PlainTextResponse
from nonebot import get_app
from nonebot_plugin_htmlrender import template_to_html
from ..nonebot_plugin_larkuser.model import UserData
from .session import get_user_forcibly
from .lang import lang

@get_app().get("/user/login/verify/success")
async def _(_request: Request, user: UserData = get_user_forcibly()) -> PlainTextResponse:
    user_id = user.user_id
    return PlainTextResponse(await template_to_html(
        Path(__file__).parent.joinpath("template").as_posix(),
        "success.html.jinja",
        title=await lang.text("success.title", user_id),
        message=await lang.text("success.message", user_id, user.nickname),
    ), media_type="text/html")