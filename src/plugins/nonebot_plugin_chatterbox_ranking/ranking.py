from nonebot_plugin_ranking import RankingData, WebRanking, register

from .__main__ import get_global_ranking_data, lang


class ChatterboxRanking(WebRanking):

    async def get_sorted_data(self, user_id: str) -> list[RankingData]:
        return await get_global_ranking_data()


register(ChatterboxRanking("chatterbox", "bar.web_title", lang))
