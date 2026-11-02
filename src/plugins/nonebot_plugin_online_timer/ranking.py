from nonebot_plugin_ranking import RankingData, WebRanking, register

from .__main__ import get_sorted_ranking_data, lang


class OnlineTimeRanking(WebRanking):

    async def get_sorted_data(self, user_id: str) -> list[RankingData]:
        return await get_sorted_ranking_data()


register(OnlineTimeRanking("online_timer", "rank.title", lang))
