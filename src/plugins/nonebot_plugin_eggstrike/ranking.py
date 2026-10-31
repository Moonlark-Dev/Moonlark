from nonebot_plugin_ranking import RankingData, WebRanking, register

from .__main__ import get_splat_ranking_data, get_throwers_ranking_data, lang


class SplatRanking(WebRanking):

    async def get_sorted_data(self, user_id: str) -> list[RankingData]:
        return await get_splat_ranking_data()


class SplatThrowersRanking(WebRanking):

    async def get_sorted_data(self, user_id: str) -> list[RankingData]:
        return await get_throwers_ranking_data()


register(SplatRanking("splat", "rank.web_title", lang))
register(SplatThrowersRanking("splat_throwers", "throwers.web_title", lang))
