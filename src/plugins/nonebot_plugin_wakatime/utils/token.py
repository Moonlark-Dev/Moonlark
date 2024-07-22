import httpx
from typing import Optional
import time
from nonebot.compat import type_validate_python
from nonebot_plugin_orm import get_session
from nonebot import logger

from .login import get_redirect_uri
from src.plugins.nonebot_plugin_wakatime.config import config
from src.plugins.nonebot_plugin_wakatime.models import TokenResponse, User


def parse_token_response(content: str) -> TokenResponse:
    logger.debug(content)
    data = {}
    for i in content.split("&"):
        d = i.split("=", 1)
        data[d[0]] = d[1]
    return type_validate_python(TokenResponse, data)


async def request_token(code: str) -> TokenResponse:
    logger.debug(code)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://wakatime.com/oauth/token",
            json={
                "client_id": config.wakatime_app_id,
                "client_secret": config.wakatime_app_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": get_redirect_uri()
            }
        )
    return parse_token_response(response.text)


async def update_token(user_id: str, response: TokenResponse) -> None:
    async with get_session() as session:
        user = User(
            user_id=user_id,
            access_token=response.access_token,
            expired_at=response.expires_in + time.time()
        )
        await session.merge(user)
        await session.commit()


async def get_token(user_id: str) -> Optional[str]:
    async with get_session() as session:
        user = await session.get(User, user_id)
        if user is not None and time.time() < user.expired_at:
            return user.access_token
