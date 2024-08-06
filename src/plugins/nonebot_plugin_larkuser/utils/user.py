from nonebot_plugin_orm import get_session
import base64
from datetime import datetime
from typing import Optional
from src.plugins.nonebot_plugin_larkuser.utils.avatar import get_user_avatar
from src.plugins.nonebot_plugin_larkuser.utils.level import get_level_by_experience
from src.plugins.nonebot_plugin_larkuser.models import UserData
from src.plugins.nonebot_plugin_larkutils import get_main_account

from ..exceptions import UserNotRegistered


class MoonlarkUser:

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.nickname = ""
        self.register_time = None
        self.ship_code = None
        self.gender = None
        self.vimcoin = 0.0
        self.experience = 0
        self.health = 100.0
        self.fav = 0.0
        self.avatar = None

    async def setup_user(self):
        self.user_id = await get_main_account(self.user_id)
        async with get_session() as session:
            user = await session.get(UserData, self.user_id)
            if user is None:
                return
            self.nickname = user.nickname
            self.register_time = user.register_time
            self.ship_code = user.ship_code
            self.gender = user.gender
            self.vimcoin = user.vimcoin
            self.experience = user.experience
            self.health = user.health
            self.fav = user.favorability
            self.avatar = await get_user_avatar(self.user_id)

    def get_nickname(self) -> str:
        return self.nickname

    def get_avatar(self) -> Optional[bytes]:
        return self.avatar

    def get_base64_avatar(self) -> Optional[str]:
        if self.has_avatar():
            return base64.b64encode(self.get_avatar()).decode()

    def has_avatar(self) -> bool:
        return self.get_avatar() is not None

    def get_fav(self) -> float:
        return self.fav

    def get_vimcoin(self) -> float:
        return max(0.0, self.vimcoin)

    def get_health(self) -> float:
        return max(self.health, 0)

    def get_gender(self) -> Optional[bool]:
        return self.gender

    def get_experience(self) -> int:
        return self.experience

    def get_register_time(self) -> Optional[datetime]:
        return self.register_time

    def get_ship_code(self) -> Optional[str]:
        return self.ship_code

    def get_level(self) -> int:
        return get_level_by_experience(self.experience)

    def is_registered(self) -> bool:
        return self.get_register_time() is not None

    async def set_data(
        self,
        user_id: str,
        experience: Optional[int] = None,
        vimcoin: Optional[float] = None,
        health: Optional[float] = None,
        favorability: Optional[float] = None,
    ) -> None:
        if not self.is_registered():
            raise UserNotRegistered
        async with get_session() as session:
            user = await session.get(UserData, self.user_id)
            if user is None:
                session.add(user := UserData(user_id=user_id, nickname=""))
            if experience:
                user.experience = experience
            if vimcoin:
                user.vimcoin = vimcoin
            if health:
                user.health = health
            if favorability:
                user.favorability = favorability
            await session.commit()
        await self.setup_user()

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


async def get_user(user_id: str) -> MoonlarkUser:
    """
    获取 Moonlark 用户
    :param user_id: 用户 ID
    :return: 可操作 Moonlark 用户类
    """
    user = MoonlarkUser(user_id)
    await user.setup_user()
    return user
