from typing import Any, AsyncGenerator, Generator

from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..nonebot_plugin_larkuser import get_user

from .lang import lang

from .jrrp import get_luck_value
from ..nonebot_plugin_larkutils import get_user_id
from .__main__ import jrrp
from ..nonebot_plugin_larkuser.model import UserData
from ..nonebot_plugin_ranking import (
    generate_image,
    RankingData,
    WebRanking,
    WebUserData
)

async def get_user_list() -> AsyncGenerator[RankingData, None]:
    session = get_session()
    result = await session.scalars(select(UserData.user_id).where(UserData.register_time != None))
    for user_id in result:
        yield {
            "user_id": user_id,
            "data": get_luck_value(user_id),
            "info": None
        }
    await session.close()



@jrrp.assign("rank")
async def _(
    user_id: str = get_user_id()
) -> None:
    image = await generate_image(
        sorted(
            [data async for data in get_user_list()],
            key=lambda x: x["data"],
            reverse=True
        ),
        user_id,
        await lang.text("rank.title", user_id)
    )
    await jrrp.finish(
        UniMessage().image(
            raw=image
        )
    )


class JrrpRank(WebRanking):
    ID = "jrrp"

    async def get_sorted_data(self) -> list[WebUserData]:
        return sorted([{
            "user_id": data["user_id"],
            "info": None,
            "data": data["data"],
            "nickname": (await get_user(data["user_id"])).nickname
        } async for data in get_user_list()], key=lambda x: x["data"], reverse=True)
