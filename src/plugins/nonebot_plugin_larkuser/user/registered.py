#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
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
from typing import Optional

from nonebot_plugin_orm import get_session

from nonebot_plugin_larkuser.exceptions import UserNotRegistered
from nonebot_plugin_larkuser.models import UserData
from nonebot_plugin_larkuser.user.base import MoonlarkUser, UnsetValue, _UNSET, _is_set
from nonebot_plugin_larkuser.utils.avatar import get_user_avatar
from nonebot_plugin_larkutils import get_main_account
import json

guest_users = {}


class MoonlarkRegisteredUser(MoonlarkUser):
    user_has_nickname: bool = True

    async def set_data(
        self,
        user_id: str,
        experience: Optional[int] = None,
        vimcoin: Optional[float] = None,
        health: Optional[float] = None,
        favorability: Optional[float] = None,
        config: Optional[dict] = None,
        downed_at: UnsetValue = _UNSET,
    ) -> None:
        if self.get_register_time() is None:
            raise UserNotRegistered
        async with get_session() as session:
            user = await session.get(UserData, self.user_id)
            if user is None:
                session.add(user := UserData(user_id=user_id, nickname=""))
            if experience is not None:
                user.experience = experience
            if vimcoin is not None:
                user.vimcoin = vimcoin
            if health is not None:
                user.health = health
            if favorability is not None:
                user.favorability = favorability
            if config is not None:
                user.config = json.dumps(config)
            if _is_set(downed_at):
                user.downed_at = downed_at
            await session.commit()
        await self.setup_user()

    async def setup_user_id(self) -> None:
        main_account = await get_main_account(self.user_id)
        if main_account != self.user_id:
            self.user_id = main_account
        self.main_account = False

    async def setup_user(self) -> None:
        await self.setup_user_id()
        async with get_session() as session:
            user = await session.get(UserData, self.user_id)
            if user is None:
                self.user_has_nickname = False
                return
            self.nickname = user.nickname
            self.register_time = user.register_time
            self.vimcoin = user.vimcoin
            self.experience = user.experience
            self.health = user.health
            self.downed_at = user.downed_at
            self.fav = user.favorability
            self.avatar = await get_user_avatar(self.user_id)
            self.config = json.loads(user.config)
        if not self.nickname:
            self.nickname = f"用户-{self.user_id}"
            self.user_has_nickname = False

    def has_nickname(self) -> bool:
        return self.user_has_nickname


class MoonlarkRegisteredGuest(MoonlarkUser):
    async def set_data(
        self,
        user_id: str,
        experience: Optional[int] = None,
        vimcoin: Optional[float] = None,
        health: Optional[float] = None,
        favorability: Optional[float] = None,
        config: Optional[dict] = None,
        downed_at: UnsetValue = _UNSET,
    ) -> None:
        user = {}
        if experience is not None:
            user["experience"] = experience
        if vimcoin is not None:
            user["vimcoin"] = vimcoin
        if health is not None:
            user["health"] = health
        if favorability is not None:
            user["favorability"] = favorability
        if config is not None:
            user["config"] = config
        if downed_at is not _UNSET:
            user["downed_at"] = downed_at

    async def setup_user_id(self) -> None:
        pass

    async def setup_user(self) -> None:
        user = guest_users.get(
            self.user_id,
            {
                "nickname": f"GUEST-{self.user_id}",
                "vimcoin": 0,
                "experience": 0,
                "health": 0,
                "favorability": 0,
                "config": {},
            },
        )
        self.nickname = user["nickname"]
        self.register_time = datetime.now()
        self.vimcoin = user["vimcoin"]
        self.experience = user["experience"]
        self.health = user["health"]
        self.fav = user["favorability"]
        self.avatar = None
        self.config = user["config"]

    def has_nickname(self) -> bool:
        return bool(self.nickname)
