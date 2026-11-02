from nonebot_plugin_ranking import RankingData, WebRanking, register

from .lang import lang
from .rank import get_sorted_luck_data


class JrrpRanking(WebRanking):

    async def get_sorted_data(self, user_id: str) -> list[RankingData]:
        return [{"user_id": uid, "data": value, "info": None} for uid, value in await get_sorted_luck_data()]


register(JrrpRanking("jrrp", "rank.title", lang))
