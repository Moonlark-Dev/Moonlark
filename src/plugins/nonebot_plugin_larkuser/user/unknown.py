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

from typing import Optional, NoReturn

from nonebot_plugin_larkuser.user.base import MoonlarkUser


class MoonlarkUnknownUser(MoonlarkUser):

    async def set_data(
        self,
        user_id: str,
        experience: Optional[int] = None,
        vimcoin: Optional[float] = None,
        health: Optional[float] = None,
        favorability: Optional[float] = None,
        config: Optional[dict] = None,
    ) -> NoReturn:
        raise TypeError("无法对未知用户（-1）执行此操作！")

    async def setup_user_id(self) -> None:
        pass

    async def setup_user(self) -> None:
        self.nickname = "未知用户"
