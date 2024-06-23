import base64
from typing import Optional, cast
from sqlalchemy.exc import NoResultFound
from fastapi import FastAPI, HTTPException, Request, status
from nonebot import get_app

from ...nonebot_plugin_larkuser.utils.user import get_user
from ...nonebot_plugin_larkuser.utils.level import get_level_by_experience
from ..types import BasicUserResponse, DetailedUserResponse
from ..session import get_user_data
from ...nonebot_plugin_larkuser.models import UserData


app = cast(FastAPI, get_app())


def get_avatar(avatar: bool, user_data: UserData) -> Optional[str]:
    return base64.b64encode(user_data.avatar).decode() if user_data.avatar is not None and avatar else None


@app.get("/api/users/me")
async def _(request: Request, avatar: bool = True, user_data: UserData = get_user_data()) -> DetailedUserResponse:
    return {
        "activation_time": user_data.activation_time.timestamp(),
        "avatar": get_avatar(avatar, user_data),
        "total_experience": user_data.experience,
        "favorability": user_data.favorability,
        "gender": user_data.gender,
        "health": user_data.health,
        "nickname": user_data.nickname,
        "level": (level := get_level_by_experience(user_data.experience)),
        "register_time": user_data.register_time.timestamp() if user_data.register_time else None,
        "ship_code": user_data.ship_code,
        "vimcoin": user_data.vimcoin,
        "user_id": user_data.user_id,
        "experience": user_data.experience - (level - 1) ** 3,
    }


@app.get("/api/users/{user_id}")
async def _(request: Request, user_id: str, avatar: bool = True) -> BasicUserResponse:
    try:
        user_data = await get_user(user_id, create=False)
    except NoResultFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return {
        "user_id": user_data.user_id,
        "nickname": user_data.nickname,
        "avatar": get_avatar(avatar, user_data),
        "level": get_level_by_experience(user_data.experience),
    }
