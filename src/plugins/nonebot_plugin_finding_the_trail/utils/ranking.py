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

from nonebot_plugin_orm import get_session
from typing import AsyncGenerator
from sqlalchemy import select
from ...nonebot_plugin_ranking import WebRanking, RankingData
from ..models import UserPoint
from ..__main__ import lang


async def get_sorted_data() -> AsyncGenerator[RankingData, None]:
    async with get_session() as session:
        for user in await session.scalars(select(UserPoint).order_by(UserPoint.points.desc())):
            yield {
                "user_id": user.user_id,
                "data": user.points
            }


class FTTRanking(WebRanking):

    async def get_sorted_data(self) -> list[RankingData]:
        return [data async for data in get_sorted_data()]


r = FTTRanking("ftt", "ranking.name", lang)
