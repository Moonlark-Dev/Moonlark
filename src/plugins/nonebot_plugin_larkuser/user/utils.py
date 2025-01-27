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
from sqlalchemy.exc import NoResultFound
from nonebot_plugin_larkutils import get_main_account

from nonebot_plugin_larkuser.models import UserData


async def is_user_registered(user_id: str, include_subaccount: bool = True):
    async with get_session() as session:
        try:
            if include_subaccount:
                user_id = await get_main_account(user_id)
            data = await session.get_one(UserData, {"user_id": user_id})
            return data.register_time is not None
        except NoResultFound:
            return False
