#  Moonlark - A new ChatBot
#  Copyright (C) 2024  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

from nonebot_plugin_ranking import WebRanking, RankingData, register
from typing import AsyncGenerator
from .api import get_user_data_list
from .lang import lang


async def get_rank_user(user_id: str) -> AsyncGenerator[RankingData, None]:
    async for user in get_user_data_list():
        yield {
            "user_id": user['user_id'],
            "data": user['total_points'],
            "info": await lang.text("rank.time", user_id, round(user["time"] / 3600, 1))
        }


class MiniGamePointRanking(WebRanking):

    async def get_sorted_data(self, user_id: str) -> list[RankingData]:
        return sorted([u async for u in get_rank_user(user_id)], key=lambda x: x["data"], reverse=True)


register(MiniGamePointRanking("minigame", "rank.title", lang))
