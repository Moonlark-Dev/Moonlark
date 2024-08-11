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
from nonebot_plugin_alconna import UniMessage
from ...nonebot_plugin_larkutils import get_user_id
from ...nonebot_plugin_ranking import generate_image
from ..__main__ import lang, ftt
from ..utils.exchange import get_exchangeable_paw_coin_count
from ..utils.ranking import get_sorted_data
from ..models import UserPoint


@ftt.assign("ranking")
async def _(user_id: str = get_user_id()) -> None:
    await ftt.finish(
        UniMessage().image(
            raw=await generate_image(
                [u async for u in get_sorted_data()], user_id, await lang.text("ranking.title", user_id)
            )
        )
    )
