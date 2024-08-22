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
from typing import AsyncGenerator

from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .session import MiniGameSession
from .models import User, UserData


async def create_minigame_session(user_id: str) -> MiniGameSession:
    """
    创建小游戏会话
    :param user_id: 挑战用户ID
    :return: 会话
    """
    session = MiniGameSession(user_id)
    await session.init_user()
    await session.add_count()
    return session


async def get_user_data(user_id: str) -> UserData:
    """
    获取用户信息
    :param user_id: 用户 ID
    :return: 用户信息
    """
    async with get_session() as session:
        if not (user := await session.get(User, user_id)):
            return UserData(user_id=user_id, total_points=0, exchanged_pawcoin=0, seconds=0, count=0)
        return UserData(
            user_id=user.user_id,
            total_points=user.total_points,
            exchanged_pawcoin=user.exchanged_pawcoin,
            seconds=user.seconds,
            count=user.count,
        )


async def get_user_list() -> list[str]:
    async with get_session() as session:
        return list(await session.scalars(select(User.user_id)))


async def get_user_data_list() -> AsyncGenerator[UserData, None]:
    for user_id in await get_user_list():
        yield await get_user_data(user_id)


async def exchange_pawcoin(user_id: str, count: int) -> None:
    async with get_session() as session:
        user = await session.get(User, user_id)
        if user:
            user.exchanged_pawcoin += count
        else:
            user = User(user_id=user_id, exchanged_pawcoin=count)
        await session.merge(user)
