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
from ..models import UserPoint


async def add_point(user_id: str, points: int) -> None:
    async with get_session() as session:
        user = await session.get(UserPoint, user_id)
        if user is None:
            user = UserPoint(user_id=user_id, points=points, count=1)
        else:
            user.points += points
            user.count += 1
        await session.merge(user)
        await session.commit()
