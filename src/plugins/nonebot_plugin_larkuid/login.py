from pathlib import Path
from typing import Optional
from fastapi import Depends, Request
from fastapi.responses import FileResponse, PlainTextResponse
from nonebot import get_app
from nonebot_plugin_htmlrender import template_to_html
from ..nonebot_plugin_larkuser.model import UserData
from .session import get_user_data, get_user_id
from .lang import lang


@get_app().get("/user/login")
async def _(request: Request, _user_id: Optional[str] = get_user_id()) -> PlainTextResponse:
    user_id = _user_id or "-1"
    return PlainTextResponse(
        await template_to_html(
            Path(__file__).parent.joinpath("template").as_posix(),
            "login.html.jinja",
            title=await lang.text("login.title", user_id),
            uid=await lang.text("login.uid", user_id),
            uid_text=await lang.text("login.uid_text", user_id),
            uid_help=await lang.text("login.uid_help", user_id),
            save_time=await lang.text("login.save_time", user_id),
            save_time_720=await lang.text("login.save_time_720", user_id),
            save_time_1=await lang.text("login.save_time_1", user_id),
            save_time_14=await lang.text("login.save_time_14", user_id),
            save_time_30=await lang.text("login.save_time_30", user_id),
            save_time_180=await lang.text("login.save_time_180", user_id),
            save_time_360=await lang.text("login.save_time_360", user_id),
            submit=await lang.text("login.submit", user_id)
        ),
        media_type="text/html"
    )
