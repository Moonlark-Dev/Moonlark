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

from datetime import datetime
from nonebot_plugin_orm import get_session
from typing import NoReturn
from nonebot.exception import FinishedException
from .models import User
from .lang import lang


class MiniGameSession:

    def __init__(self, user_id: str) -> None:
        """
        初始化小游戏会话
        :param user_id: 用户 ID
        """
        self.user_id = user_id
        self.start_time = datetime.now()

    async def quit(self) -> NoReturn:
        await lang.finish("quit.quit", self.user_id)
        raise FinishedException

    async def finish(self) -> int:
        """
        标记小游戏结束
        :return: 挑战时间
        """
        end_time = datetime.now()
        time = round((end_time - self.start_time).total_seconds())
        async with get_session() as session:
            user = await session.get_one(User, self.user_id)
            user.seconds += time
            await session.commit()
        return time

    async def add_points(self, points: int) -> int:
        """
        添加小游戏积分
        :return: 实际增加的积分
        :param points: 积分数量
        """
        async with get_session() as session:
            user = await session.get_one(User, self.user_id)
            user.total_points += points
            await session.commit()
        return points

    async def init_user(self):
        """
        初始化用户数据库数据
        """
        async with get_session() as session:
            if not await session.get(User, self.user_id):
                session.add(User(user_id=self.user_id))
                await session.commit()
