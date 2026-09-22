from nonebot_plugin_ranking.web import WebRanking, register
from nonebot_plugin_ranking.types import RankingData
from ..models import QuickMathUser, QuickMathWeek
from ..__main__ import lang

from nonebot_plugin_orm import get_session
from sqlalchemy import select
from typing import Any, AsyncGenerator

from .user import get_week_key


async def get_user_list(order_by: Any = QuickMathUser.max_point) -> AsyncGenerator[QuickMathUser, None]:
    async with get_session() as session:
        data = await session.scalars(select(QuickMathUser).order_by(order_by.desc()))
        for user in data:
            yield user


async def get_weekly_user_list(user_id: str, limit: int = 5) -> tuple[list[QuickMathWeek], int]:
    """获取本周积分排行前 ``limit`` 名，以及当前用户的本周积分。"""
    week = get_week_key()
    my_points = 0
    async with get_session() as session:
        data = await session.scalars(
            select(QuickMathWeek)
            .where(QuickMathWeek.week == week)
            .order_by(QuickMathWeek.points.desc(), QuickMathWeek.user_id)
            .limit(limit),
        )
        ranked = list(data)
        mine = await session.get(QuickMathWeek, (user_id, week))
        if mine is not None:
            my_points = mine.points
    return ranked, my_points


class RecordRanking(WebRanking):
    async def get_sorted_data(self, user_id: str) -> list[RankingData]:
        return [
            {
                "user_id": user.user_id,
                "data": user.max_point,
                "info": None,
            }
            async for user in get_user_list()
        ]


class TotalRanking(WebRanking):
    async def get_sorted_data(self, user_id: str) -> list[RankingData]:
        return [
            {
                "user_id": user.user_id,
                "data": user.experience,
                "info": None,
            }
            async for user in get_user_list(QuickMathUser.experience)
        ]


register(RecordRanking("quick_math_record", "rank.title-1", lang))
register(TotalRanking("quick_math_total", "rank.title-2", lang))
