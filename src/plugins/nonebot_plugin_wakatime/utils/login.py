import asyncio
from typing import Optional
from fastapi import Query, Request, HTTPException, status
from nonebot import get_app

from ..__main__ import lang
from ..config import config

logining_user_id: Optional[str] = None
logining_user_code: Optional[str] = None


def get_redirect_uri() -> str:
    return f"{config.moonlark_api_base}/api/wakatime/login"


async def request_login(user_id: str) -> None:
    global logining_user_id
    if logining_user_id is not None:
        await lang.finish("login.wait", user_id)
    logining_user_id = user_id
    await lang.send(
        "login.go",
        user_id,
        config.wakatime_app_id,
        get_redirect_uri(),
        limit=config.wakatime_login_timeout
    )


@get_app().get("/api/wakatime/login")
async def _(
        _req: Request,
        code: Optional[str] = Query(None),
) -> None:
    global logining_user_code
    if logining_user_id is None or code is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST)
    logining_user_code = code


def clean() -> None:
    global logining_user_code, logining_user_id
    logining_user_code = None
    logining_user_id = None


async def wait_user_code() -> Optional[str]:
    for i in range(config.wakatime_login_timeout):
        await asyncio.sleep(1)
        if logining_user_code is not None:
            return logining_user_code
