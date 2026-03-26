from typing import Optional

from nonebot_plugin_render.render import render_template
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkuser.models import UserData
from .lang import lang
from .types import RankingData, UserDataWithIndex


async def find_user(ranked_data: list[RankingData], user_id: str) -> Optional[UserDataWithIndex]:
    index = 0
    for data in ranked_data:
        index += 1
        if data["user_id"] == user_id:
            return {
                "nickname": (await get_user(user_id)).get_nickname(),
                "user_id": user_id,
                "data": data["data"],
                "index": index,
                "info": data["info"] or await lang.text("image.info", user_id, data["user_id"]),
            }


async def get_users(ranked_data: list[RankingData], user_id: str, limit: int = 12) -> list[UserData]:
    users = []
    for data in ranked_data[:limit]:
        user = await get_user(data["user_id"])
        if data["info"] is None and not user.has_nickname():
            nickname = await lang.text("image.default_nickname", user_id)
        else:
            nickname = user.get_nickname()
        users.append(
            {
                "nickname": nickname,
                "info": data["info"] or await lang.text("image.info", user_id, data["user_id"]),
                "data": data["data"],
            }
        )
    return users


async def generate_image(ranked_data: list[RankingData], user_id: str, title: str, limit: int = 12) -> bytes:
    return await render_template(
        "ranking.html.jinja",
        title,
        user_id,
        {
            "me": await find_user(ranked_data, user_id),
            "users": await get_users(ranked_data, user_id, limit),
        },
    )
