from nonebot_plugin_ranking import RankingData, WebRanking, register

from .__main__ import get_sorted_ranking_data, lang


class FavorabilityRanking(WebRanking):

    async def get_sorted_data(self, user_id: str) -> list[RankingData]:
        return await get_sorted_ranking_data()


register(FavorabilityRanking("fav", "fav_rank.title", lang))
