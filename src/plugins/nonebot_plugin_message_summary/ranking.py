from nonebot_plugin_orm import get_session
from nonebot_plugin_ranking import RankingData, WebRanking, register
from sqlalchemy import func, select

from .lang import lang
from .models import MVPRecord


async def get_mvp_ranking_data(user_id: str) -> list[RankingData]:
    """跨群汇总各用户的 MVP 次数，供 WebRanking 使用。"""
    total = func.sum(MVPRecord.mvp_count).label("total_mvp")
    group_count = func.count(MVPRecord.group_id).label("group_count")
    async with get_session() as session:
        rows = (
            await session.execute(
                select(MVPRecord.user_id, total, group_count).group_by(MVPRecord.user_id).order_by(total.desc()),
            )
        ).all()
    return [
        {
            "user_id": row.user_id,
            "data": row.total_mvp,
            "info": await lang.text("mvp_ranking.web_info", user_id, row.group_count),
        }
        for row in rows
    ]


class MVPRanking(WebRanking):

    async def get_sorted_data(self, user_id: str) -> list[RankingData]:
        return await get_mvp_ranking_data(user_id)


register(MVPRanking("mvp", "mvp_ranking.web_title", lang))
