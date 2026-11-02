from nonebot_plugin_ranking import RankingData, WebRanking, register

from .__main__ import get_avg_ranking_data, get_rise_ranking_data, lang


class RiseRanking(WebRanking):

    async def get_sorted_data(self, user_id: str) -> list[RankingData]:
        return await get_rise_ranking_data(user_id)


class RiseAvgRanking(WebRanking):

    async def get_sorted_data(self, user_id: str) -> list[RankingData]:
        return await get_avg_ranking_data(user_id)


register(RiseRanking("wakeuprank", "wakeuprank.title", lang))
register(RiseAvgRanking("wakeuprank_avg", "wakeuprank.avg_title", lang))
