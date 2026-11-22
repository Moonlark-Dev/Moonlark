from nonebot_plugin_ranking import RankingData, WebRanking, register

from .lang import lang
from .rank import get_ranking_data


class TurtleSoupRanking(WebRanking):

    async def get_sorted_data(self, _user_id: str) -> list[RankingData]:
        return await get_ranking_data()


register(TurtleSoupRanking("turtle-soup", "announce.rank", lang))
