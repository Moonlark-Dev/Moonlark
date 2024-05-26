from fastapi import Request
from nonebot import get_app
from ..nonebot_plugin_larkuid.session import get_user_forcibly


@get_app().get("/api/set_language")
async def _(_request: Request, language: str) -> None:
    ...