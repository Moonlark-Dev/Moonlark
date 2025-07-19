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

from typing import Any
import base64
from datetime import datetime
from typing import Optional, TypeVar
from abc import ABC, abstractmethod
from nonebot_plugin_larkuser.utils.level import get_level_by_experience

T = TypeVar("T")


class MoonlarkUser(ABC):

    def __init__(self, user_id: str):
        self.user_id = user_id

        self.register_time: Optional[datetime] = None
        self.avatar: Optional[bytes] = None

        self.nickname = ""
        self.vimcoin = 0.0
        self.experience = 0
        self.health = 100.0
        self.fav = 0.0
        self.main_account = True
        self.config = {}

    @abstractmethod
    async def setup_user(self):
        pass

    @abstractmethod
    async def setup_user_id(self) -> None:
        pass

    def is_main_account(self) -> bool:
        return self.main_account

    def get_nickname(self) -> str:
        return self.nickname

    def has_nickname(self) -> bool:
        return bool(self.nickname)

    def get_avatar(self) -> Optional[bytes]:
        return self.avatar

    def get_base64_avatar(self) -> Optional[str]:
        if self.has_avatar():
            return base64.b64encode(self.get_avatar()).decode()
        return None

    def has_avatar(self) -> bool:
        return self.get_avatar() is not None

    def get_fav(self) -> float:
        return self.fav

    def get_vimcoin(self) -> float:
        return max(0.0, self.vimcoin)

    def get_health(self) -> float:
        return max(self.health, 0)


    def get_experience(self) -> int:
        return self.experience

    def get_register_time(self) -> Optional[datetime]:
        return self.register_time

    def get_level(self) -> int:
        return get_level_by_experience(self.experience)

    def is_registered(self) -> bool:
        return self.get_register_time() is not None

    @abstractmethod
    async def set_data(
        self,
        user_id: str,
        experience: Optional[int] = None,
        vimcoin: Optional[float] = None,
        health: Optional[float] = None,
        favorability: Optional[float] = None,
        config: Optional[dict] = None,
    ) -> None:
        pass

    async def add_fav(self, count: float) -> None:
        await self.set_data(self.user_id, favorability=self.fav + count)

    async def add_experience(self, count: int) -> None:
        await self.set_data(self.user_id, experience=self.experience + count)

    async def add_vimcoin(self, count: float) -> None:
        await self.set_data(self.user_id, vimcoin=self.vimcoin + count)

    async def use_vimcoin(self, count: float) -> None:
        await self.set_data(self.user_id, vimcoin=self.vimcoin + count)

    async def has_vimcoin(self, count: float) -> bool:
        return self.vimcoin >= count

    def get_config_key(self, key: str, default: Optional[T] = None) -> T:
        return self.config.get(key, default)

    async def set_config_key(self, key: str, value: Any) -> None:
        self.config[key] = value
        await self.set_data(self.user_id, config=self.config)
