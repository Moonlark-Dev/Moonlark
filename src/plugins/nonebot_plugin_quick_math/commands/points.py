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
from nonebot_plugin_larkutils import get_user_id
from ..__main__ import quick_math
from nonebot_plugin_finding_the_trail.__main__ import lang
from ..models import QuickMathUser


@quick_math.assign("points")
async def _(user_id: str = get_user_id()) -> None:
    async with get_session() as session:
        user_point = await session.get(QuickMathUser, user_id)
        if user_point is None:
            await lang.finish("points.no_points", user_id)
            return
        await lang.finish(
            "points.info",
            user_id,
            user_point.exchanged,
            user_point.experience,
            user_point.exchanged,
            at_sender=False,
            reply_message=True,
        )
