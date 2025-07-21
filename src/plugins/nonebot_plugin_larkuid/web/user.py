from typing import cast, Optional

from nonebot_plugin_orm import get_session
from sqlalchemy.exc import NoResultFound
from fastapi import FastAPI, HTTPException, Request, status
from nonebot import get_app

from nonebot_plugin_larkuser.models import UserData
from nonebot_plugin_larkuser.utils.user import get_user
from nonebot_plugin_larkutils import review_text
from ..types import BasicUserResponse, DetailedUserResponse, MessageResponse
from ..session import get_user_data
from nonebot_plugin_larkuser.user.base import MoonlarkUser

app = cast(FastAPI, get_app())


@app.get("/api/users/me")
async def _(request: Request, avatar: bool = True, user_data: MoonlarkUser = get_user_data()) -> DetailedUserResponse:
    reg_time = user_data.get_register_time()
    return {
        "avatar": user_data.get_base64_avatar(),
        "total_experience": user_data.get_experience(),
        "favorability": user_data.get_fav(),
        "health": user_data.get_health(),
        "nickname": user_data.get_nickname(),
        "level": user_data.get_level(),
        "register_time": reg_time.timestamp() if reg_time else None,
        "vimcoin": user_data.get_vimcoin(),
        "user_id": user_data.user_id,
        "experience": user_data.get_experience() - (user_data.get_level() - 1) ** 3,
    }


@app.post("/api/users/me")
async def _(
    request: Request, nickname: Optional[str] = None, user_data: MoonlarkUser = get_user_data()
) -> MessageResponse:
    async with get_session() as session:
        user = await session.get(UserData, {"user_id": user_data.user_id})
        if user is None:
            return {"success": False, "message": "未找到用户"}
        if nickname is not None:
            if (r := await review_text(nickname))["conclusion"]:
                user.nickname = nickname if nickname else None
            else:
                return {"success": False, "message": f"审核未通过: {r['message']}"}
        await session.commit()
    return {"success": True, "message": "执行过程中未出现异常"}


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
