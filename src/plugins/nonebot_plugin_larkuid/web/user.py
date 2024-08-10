from typing import cast
from sqlalchemy.exc import NoResultFound
from fastapi import FastAPI, HTTPException, Request, status
from nonebot import get_app

from ...nonebot_plugin_larkuser.utils.user import get_user
from ..types import BasicUserResponse, DetailedUserResponse
from ..session import get_user_data
from ...nonebot_plugin_larkuser import MoonlarkUser


app = cast(FastAPI, get_app())


@app.get("/api/users/me")
async def _(request: Request, avatar: bool = True, user_data: MoonlarkUser = get_user_data()) -> DetailedUserResponse:
    reg_time = user_data.get_register_time()
    return {
        "avatar": user_data.get_base64_avatar(),
        "total_experience": user_data.get_experience(),
        "favorability": user_data.get_fav(),
        "gender": user_data.get_gender(),
        "health": user_data.get_health(),
        "nickname": user_data.get_nickname(),
        "level": user_data.get_level(),
        "register_time": reg_time.timestamp() if reg_time else None,
        "ship_code": user_data.get_ship_code(),
        "vimcoin": user_data.get_vimcoin(),
        "user_id": user_data.user_id,
        "experience": user_data.get_experience() - (user_data.get_level() - 1) ** 3,
    }


@app.get("/api/users/{user_id}")
async def _(request: Request, user_id: str, avatar: bool = True) -> BasicUserResponse:
    try:
        user_data = await get_user(user_id)
    except NoResultFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return {
        "user_id": user_data.user_id,
        "nickname": user_data.get_nickname(),
        "avatar": user_data.get_base64_avatar() if avatar else None,
        "level": user_data.get_level(),
    }
