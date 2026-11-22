"""正确作答数排行榜的数据查询：指令与网页榜单共用。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nonebot_plugin_larkuser import get_user
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .models import TurtleSoupPlayer

if TYPE_CHECKING:
    from nonebot_plugin_ranking import RankingData


async def get_ranking_data() -> list[RankingData]:
    """按正确作答数从高到低返回排行数据（只统计答对过至少一局的人）。"""
    async with get_session() as session:
        rows = (
            await session.scalars(
                select(TurtleSoupPlayer)
                .where(TurtleSoupPlayer.correct_count > 0)
                .order_by(TurtleSoupPlayer.correct_count.desc(), TurtleSoupPlayer.last_correct_time.asc()),
            )
        ).all()
    return [{"user_id": row.user_id, "data": row.correct_count, "info": None} for row in rows]


async def get_rank_display(
    user_id: str,
    limit: int = 10,
) -> tuple[list[tuple[str, int]], int | None, int]:
    """返回 ``(前 limit 名的 (昵称, 答对数), 我的名次, 我的答对数)``。"""
    rows = await get_ranking_data()
    my_index: int | None = None
    my_count = 0
    top: list[tuple[str, int]] = []
    for index, item in enumerate(rows, 1):
        if item["user_id"] == user_id:
            my_index = index
            my_count = int(item["data"])
        if index > limit:
            continue
        try:
            nickname = (await get_user(item["user_id"])).get_nickname()
        except Exception:
            nickname = item["user_id"]
        top.append((nickname, int(item["data"])))
    return top, my_index, my_count
