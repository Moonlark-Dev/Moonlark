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

from nonebot_plugin_larkuser.user.registered import MoonlarkRegisteredUser


class MoonlarkGuestUser(MoonlarkRegisteredUser):

    def __init__(self, user_id: str):
        super().__init__(user_id)
        self.original_user_id = user_id
        self.user_has_nickname = False

    async def setup_user_id(self) -> None:
        self.user_id = -1
        self.main_account = False

    async def setup_user(self) -> None:
        await super().setup_user()
        if not self.nickname:
            self.nickname = f"Guest用户-{self.original_user_id}"
        else:
            self.user_has_nickname = True
        
    def has_nickname(self) -> bool:
        return self.user_has_nickname
