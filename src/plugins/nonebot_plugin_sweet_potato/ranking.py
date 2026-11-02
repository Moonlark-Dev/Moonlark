from nonebot_plugin_ranking import RankingData, WebRanking, register

from .lang import lang
from .room import get_rank_data


class SweetPotatoHoldRanking(WebRanking):
    async def get_sorted_data(self, user_id: str) -> list[RankingData]:
        return await get_rank_data(user_id)


register(SweetPotatoHoldRanking("sweet_potato_hold", "rank.title", lang))
