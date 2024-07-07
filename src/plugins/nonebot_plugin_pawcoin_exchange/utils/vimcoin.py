from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ...nonebot_plugin_larkuser.models import UserData


async def get_total_vimcoin() -> float:
    count = 0
    async with get_session() as session:
        for c in await session.scalars(select(UserData.vimcoin)):
            count += c
    return count
