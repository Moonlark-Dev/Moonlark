from fastapi import Request
from nonebot import get_app
from nonebot_plugin_orm import get_scoped_session

from ...nonebot_plugin_larklang.__main__ import set_user_language
from ...nonebot_plugin_larkuser.models import UserData
from ..session import get_user_forcibly


@get_app().get("/api/set_language", status_code=204)
async def _(_request: Request, language: str, user: UserData = get_user_forcibly()) -> None:
    await set_user_language(user.user_id, language, get_scoped_session())
