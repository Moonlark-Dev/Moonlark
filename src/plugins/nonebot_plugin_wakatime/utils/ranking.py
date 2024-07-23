from nonebot_plugin_orm import get_session
from sqlalchemy import select
from typing import AsyncGenerator, Optional
from src.plugins.nonebot_plugin_ranking import RankingData, WebRanking

from ..__main__ import lang
from .stats import get_user_stats
from ..models import StatsData, User


async def get_user_list() -> AsyncGenerator[tuple[str, StatsData], None]:
    async with get_session() as session:
        data = await session.scalars(select(User.user_id))
        for user_id in data:
            if (durations := await get_user_stats(user_id)) is not None:
                yield user_id, durations.data


async def get_ranking_users() -> AsyncGenerator[RankingData, None]:
    async for user_id, durations in get_user_list():
        yield {
            "user_id": user_id,
            "data": round(durations.total_seconds / 3600, 1),
            "info": await lang.text(
                "ranking.info", user_id, durations.username, durations.human_readable_total, durations.projects[0].name
            ),
        }


async def get_sorted_ranking_data() -> list[RankingData]:
    return sorted([u async for u in get_ranking_users()], key=lambda x: x["data"], reverse=True)


class WakaTimeRanking(WebRanking):
    ID = "wakatime"
    NAME = "ranking.info"
    LANG = lang

    async def get_sorted_data(self) -> list[RankingData]:
        return await get_sorted_ranking_data()


async def get_user_ranking(user_id: str) -> Optional[int]:
    ranking = 1
    for user in await get_sorted_ranking_data():
        if user["user_id"] == user_id:
            return ranking
        ranking += 1
