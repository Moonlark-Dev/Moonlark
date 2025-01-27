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
from nonebot_plugin_alconna import Match
from nonebot_plugin_larkutils import get_user_id
from ..__main__ import quick_math
from nonebot_plugin_finding_the_trail.utils.exchange import get_exchangeable_paw_coin_count
from nonebot_plugin_finding_the_trail.__main__ import lang
from ..models import QuickMathUser
from nonebot_plugin_bag.utils.give import give_item_by_data


@quick_math.assign("exchange")
async def _(count: Match[int], user_id: str = get_user_id()) -> None:
    async with get_session() as session:
        user_point = await session.get(QuickMathUser, user_id)
        if user_point is None:
            await lang.finish("points.no_points", user_id)
            return
        exchangeable = get_exchangeable_paw_coin_count(user_point.experience, user_point.exchanged)
        count = count.result if count.available else exchangeable
        if count > exchangeable or count <= 0:
            await lang.finish("exchange.no_points", user_id, exchangeable)
        await give_item_by_data(
            user_id,
            {"experience": 0, "vimcoin": 0, "items": [{"item_id": "moonlark:pawcoin", "count": count, "data": {}}]},
        )
        user_point.exchanged += count
        await session.commit()
        await lang.finish("exchange.ok", user_id, count)
