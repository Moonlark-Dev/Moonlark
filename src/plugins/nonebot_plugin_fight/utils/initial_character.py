#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
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

from datetime import datetime

from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..models import Character as CharacterData


async def init_user_character(user_id: str) -> None:
    async with get_session() as session:
        if not await session.scalar(select(CharacterData).where(CharacterData.user_id == user_id)):
            session.add(
                CharacterData(
                    user_id=user_id,
                    character_type=2,
                    experience=0,
                    fav=-1,
                    get_time=datetime.now(),
                    hp_percent=100,
                    weapon_experience=0,
                    weapon_damage=0,
                )
            )
            await session.commit()
