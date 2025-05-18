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
import math
import random
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_bag.utils.bag import give_special_item
from nonebot_plugin_orm import get_session
from nonebot.matcher import Matcher
from typing import Callable, NoReturn, Optional, TypeVar
from nonebot_plugin_larkuser.utils.waiter import prompt
from .models import UserGameData
from .lang import lang
from sqlalchemy import select

T = TypeVar("T")


class MiniGameSession:

    def __init__(self, user_id: str, game_id: str) -> None:
        """
        初始化小游戏会话
        :param user_id: 用户 ID
        """
        self.user_id = user_id
        self.start_time = datetime.now()
        self.game_type = game_id

    async def write_user_data(self, add_points: int, seconds: int) -> None:
        """
        写入用户数据
        :param add_points: 增加的分数
        :param seconds: 挑战时间
        """
        async with get_session() as session:
            user_data = await session.scalar(
                select(UserGameData).where(
                    UserGameData.user_id == self.user_id, UserGameData.minigame_id == self.game_type
                )
            )
            if user_data is None:
                user_data = UserGameData(
                    user_id=self.user_id,
                    minigame_id=self.game_type,
                    total_points=add_points,
                    play_seconds=seconds,
                    success_count=1,
                )
                session.add(user_data)
            else:
                user_data.total_points += add_points
                user_data.play_seconds += seconds
                user_data.success_count += 1
            await session.commit()

    async def quit(self, text: Optional[str] = None, matcher: Matcher = Matcher()) -> NoReturn:
        if text is not None:
            await matcher.finish(text)
        await lang.finish("quit.quit", self.user_id)

    async def finish(self, game_point: int = 100, rate: float = 1) -> tuple[int, int]:
        """
        标记小游戏结束
        :return: 挑战时间, 挑战分数
        """
        end_time = datetime.now()
        time = round((end_time - self.start_time).total_seconds())
        point = round(game_point * rate * get_time_rt(time))
        await self.write_user_data(point, time)
        await self.gain_vimcoin(point, rate)
        return time, point

    async def get_input(
        self,
        message: str | UniMessage,
        checker: Optional[Callable[[str], bool]] = None,
        parser: Callable[[str], T] = lambda msg: msg,
    ) -> T:
        return await prompt(message, self.user_id, checker, parser=parser)

    async def gain_vimcoin(self, point: int, rate: float) -> None:
        if point <= 25:
            return
        elif point <= 50:
            count = 5
        elif point <= 100:
            count = 10
        else:
            r_2 = random.choice([0.87, 0.75, 0.75, 0.6, 0.6, 0.5, 0.5, 0.5, 0.43, 0.41, 0.3])
            count = round((5 * math.log(point / 2 - 49, 2) + 10) * rate * r_2)
        await give_special_item(self.user_id, "vimcoin", count, {})
        await lang.send("gain", self.user_id, count)


def get_time_rt(sec: int) -> float:
    minute = round(sec / 60)
    return 0.015 * minute**2 - 0.156 * minute + 1.2
