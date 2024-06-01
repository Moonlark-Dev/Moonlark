from pathlib import Path
from typing import Optional

from nonebot_plugin_htmlrender import template_to_pic

from ..nonebot_plugin_larkuser import get_user
from ..nonebot_plugin_larkuser.models import UserData
from ..nonebot_plugin_larkutils.html import escape_html
from .lang import lang
from .types import RankingData, UserDataWithIndex


async def find_user(ranked_data: list[RankingData], user_id: str) -> Optional[UserDataWithIndex]:
    index = 0
    for data in ranked_data:
        index += 1
        if data["user_id"] == user_id:
            return {
                "nickname": escape_html((await get_user(user_id)).nickname),
                "data": data["data"],
                "index": index,
                "info": escape_html(data["info"] or await lang.text("image.info", user_id, data["user_id"])),
            }


async def get_users(ranked_data: list[RankingData], user_id: str, limit: int = 12) -> list[UserData]:
    users = []
    for data in ranked_data[:limit]:
        users.append(
            {
                "nickname": escape_html((await get_user(data["user_id"])).nickname),
                "info": escape_html(data["info"] or await lang.text("image.info", user_id, data["user_id"])),
                "data": data["data"],
            }
        )
    return users


async def generate_image(ranked_data: list[RankingData], user_id: str, title: str, limit: int = 12) -> bytes:
    templates = {
        "title": title,
        "footer": await lang.text("image.footer", user_id),
        "me": await find_user(ranked_data, user_id),
        "users": await get_users(ranked_data, user_id, limit),
    }
    return await template_to_pic(Path(__file__).parent.joinpath("templates").as_posix(), "command.html.jinja", templates)
