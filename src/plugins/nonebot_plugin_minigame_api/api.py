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


from typing import AsyncGenerator, TypedDict

from sqlalchemy import select
from sympy import use

from .models import UserGameData
from nonebot_plugin_orm import get_session
from .session import MiniGameSession


async def create_minigame_session(user_id: str, game_id: str) -> MiniGameSession:
    """
    创建小游戏会话
    :param user_id: 挑战用户ID
    :return: 会话
    """
    session = MiniGameSession(user_id, game_id)
    return session


class DictUserGameData(TypedDict):
    user_id: str
    total_points: int
    time: int


async def get_user_data_list() -> AsyncGenerator[DictUserGameData, None]:
    """
    获取用户数据列表
    :return: 用户数据列表
    """
    async with get_session() as session:
        for user_id in await session.scalars(select(UserGameData.user_id).distinct()):
            user_data: DictUserGameData = {"user_id": user_id, "total_points": 0, "time": 0}
            for data in await session.scalars(select(UserGameData).where(UserGameData.user_id == user_id)):
                user_data["total_points"] += data.total_points
                user_data["time"] += data.play_seconds
            yield user_data
