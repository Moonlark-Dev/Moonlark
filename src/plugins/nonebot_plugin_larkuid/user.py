from datetime import datetime
from pathlib import Path
from fastapi import Request
from fastapi.responses import PlainTextResponse
from nonebot import get_app, require
from nonebot_plugin_htmlrender import template_to_html
from ..nonebot_plugin_larkuser.utils.gsc_time import get_galactic_time
from ..nonebot_plugin_larklang.__main__ import get_languages, get_user_language
from ..nonebot_plugin_larkuser.utils.level import get_level_by_experience
from ..nonebot_plugin_larkutils.html import escape_html
from .session import get_user_forcibly
from ..nonebot_plugin_larkuser.model import UserData
from ..nonebot_plugin_larkuser.lang import lang


@get_app().get("/user")
async def _(_request: Request, user: UserData = get_user_forcibly()):
    now = datetime.now()
    level = get_level_by_experience(user.experience)
    return PlainTextResponse(
        await template_to_html(
            Path(__file__).parent.joinpath("template").as_posix(),
            "user.html.jinja",
            title=await lang.text("web.title", user.user_id),
            username=escape_html(user.nickname),
            uid=await lang.text("web.uid", user.user_id, user.user_id),
            total_exp=await lang.text("web.total_exp", user.user_id, user.experience),
            level=await lang.text("web.level", user.user_id, level, user.experience - (level - 1) ** 3, level ** 3),
            vimcoin=await lang.text("web.vimcoin", user.user_id, round(user.vimcoin, 3)),
            fav=await lang.text("web.fav", user.user_id, round(user.favorability, 3)),
            hp=await lang.text("web.hp", user.user_id, user.health),
            time=await lang.text("web.time", user.user_id),
            earth_time=await lang.text("web.earth_time", user.user_id, now.strftime("%Y-%m-%d %H:%M:%S")),
            gsc_time=await lang.text("web.gsc_time", user.user_id, *get_galactic_time(now.timestamp())),
            i18n=await lang.text("web.i18n", user.user_id),
            current_lang=await lang.text("web.current_lang", user.user_id),
            lang_list=[{
                "name": lang,
                "selected": lang == await get_user_language(user.user_id)
            } for lang in get_languages().keys()],
            registry=await lang.text("web.registry", user.user_id),
            activate_time=await lang.text(
                "web.activate_time",
                user.user_id,
                user.activation_time.strftime("ET %Y-%m-%d")
            ),
            registry_time=await lang.text(
                "web.registry_time",
                user.user_id,
                (user.register_time or datetime.fromtimestamp(0)).strftime(
                    "ET %Y-%m-%d"
                )
            )
        ),
        media_type="text/html"
    )
