from pathlib import Path
from fastapi import Request
from fastapi.responses import PlainTextResponse
from nonebot import get_app
from nonebot_plugin_htmlrender import template_to_html
from nonebot_plugin_orm import get_scoped_session
from sqlalchemy import select
from .model import SubjectData
from ..nonebot_plugin_larkuid.session import get_user_id_forcibly
from .lang import lang


@get_app().get("/user/access")
async def _(_request: Request, user_id: str = get_user_id_forcibly()) -> PlainTextResponse:
    session = get_scoped_session()
    perms = [{
        "available": item.available,
        "name": item.name
    } for item in (await session.scalars(
        select(SubjectData)
        .where(SubjectData.subject == user_id)
    )).all()]
    return PlainTextResponse(await template_to_html(
        Path(__file__).parent.joinpath("template").as_posix(),
        "access.html.jinja",
        title=await lang.text("web.title", user_id),
        info=await lang.text("web.info", user_id),
        have=await lang.text("web.have", user_id),
        do_not_have=await lang.text("web.do_not_have", user_id),
        perms=perms
    ), media_type="text/html")
