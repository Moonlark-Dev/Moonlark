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

from typing import Any
import base64
from datetime import datetime, timedelta
from typing import Optional, TypeAlias, TypeGuard, TypeVar
from abc import ABC, abstractmethod
from nonebot_plugin_orm import get_session
from nonebot_plugin_larkuser.utils.level import get_level_by_experience
from nonebot_plugin_larkuser.models import UserDeathRecord
from nonebot_plugin_larkuser.lang import lang

T = TypeVar("T")


class _UnsetSentinel:
    """set_data 中表示「不修改该字段」的哨兵值，区别于 None（None 表示显式清空）"""


_UNSET = _UnsetSentinel()
UnsetValue: TypeAlias = datetime | None | _UnsetSentinel


def _is_set(value: UnsetValue) -> TypeGuard[datetime | None]:
    """判断是否为「显式设置」的 downed_at 值（哨兵之外的 datetime 或 None）"""
    return value is not _UNSET


MAX_HEALTH = 100
REVIVE_HEALTH = 5
DOWN_DURATION = timedelta(minutes=30)


FAV_LEVELS = [
    (0.005, "stranger"),  # 素昧平生
    (0.050, "acquaintance"),  # 点头之交
    (0.150, "familiar"),  # 熟客
    (0.300, "close_friend"),  # 挚友
    (float("inf"), "cyber_partner"),  # 赛博伴侣
]


class MoonlarkUser(ABC):
    def __init__(self, user_id: str):
        self.user_id = user_id

        self.register_time: Optional[datetime] = None
        self.avatar: Optional[bytes] = None

        self.nickname = ""
        self.vimcoin = 0.0
        self.experience = 0
        self.health = 100.0
        self.downed_at: Optional[datetime] = None
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
        return self.nickname or f"匿名-{self.user_id[-4:]}"

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

    def get_display_fav(self) -> int:
        """返回好感度乘以 1000 后取整，用于展示"""
        return round(self.get_fav() * 1000)

    def _get_fav_level_key(self) -> str:
        """
        根据好感度值确定好感等级的语言键

        0.000 - 0.005: 素昧平生 (stranger)
        0.006 - 0.050: 点头之交 (acquaintance)
        0.051 - 0.150: 熟客 (familiar)
        0.151 - 0.300: 挚友 (close_friend)
        0.301+: 赛博伴侣 (cyber_partner)
        """
        for threshold, level_key in FAV_LEVELS:
            if self.fav <= threshold:
                return level_key
        return FAV_LEVELS[-1][1]  # 默认返回最高等级

    async def get_fav_level(self) -> str:
        """获取本地化后的好感等级名称"""
        level_key = self._get_fav_level_key()
        return await lang.text(f"fav_level.{level_key}", self.user_id)

    def get_vimcoin(self) -> float:
        return max(0.0, self.vimcoin)

    def get_health(self) -> float:
        return max(0.0, min(float(self.health), MAX_HEALTH))

    def get_experience(self) -> int:
        return self.experience

    def get_register_time(self) -> Optional[datetime]:
        return self.register_time

    def get_level(self) -> int:
        return get_level_by_experience(self.experience)

    def is_registered(self) -> bool:
        return self.get_register_time() is not None

    def get_down_remaining(self) -> timedelta:
        """返回倒地剩余时间，未倒地时返回零时长"""
        if self.downed_at is None:
            return timedelta(0)
        return max(DOWN_DURATION - (datetime.now() - self.downed_at), timedelta(0))

    async def is_down(self) -> bool:
        """是否处于倒地状态。

        已注册用户 HP 为 0 且倒地未超过 30 分钟时为倒地状态。
        倒地状态持续 30 分钟，结束后将 HP 重置为 5 并复活。
        """
        if self.get_register_time() is None or self.get_health() > 0 or self.downed_at is None:
            return False
        if datetime.now() - self.downed_at >= DOWN_DURATION:
            await self.revive()
            return False
        return True

    async def set_health(self, value: float) -> None:
        """设置血量，限制在 0 ~ MAX_HEALTH。

        血量降到 0 时进入倒地状态并记录一次死亡；血量恢复时清除倒地状态。
        """
        value = max(0.0, min(float(value), MAX_HEALTH))
        if value > 0 and self.downed_at is not None:
            await self.set_data(self.user_id, health=value, downed_at=None)
        elif value == 0 and self.get_health() > 0:
            await self.set_data(self.user_id, health=0, downed_at=datetime.now())
            await self.increase_death_count()
        else:
            await self.set_data(self.user_id, health=value)

    async def heal(self, amount: float) -> None:
        """回复血量，amount 必须为非负数"""
        if amount < 0:
            raise ValueError(f"heal 的血量数值不能为负数：{amount}")
        await self.set_health(self.get_health() + amount)

    async def damage(self, amount: float) -> bool:
        """扣除血量，amount 必须为非负数。

        血量不足时不会「不进行任何操作」，而是直接将 HP 扣到 0 触发倒地，
        并返回 False（表示未足额扣除）。
        """
        if amount < 0:
            raise ValueError(f"damage 的血量数值不能为负数：{amount}")
        if self.get_health() < amount:
            await self.set_health(0)
            return False
        await self.set_health(self.get_health() - amount)
        return True

    async def revive(self) -> None:
        """倒地状态结束，将 HP 重置为 5 并清除倒地状态"""
        if self.get_register_time() is None:
            return
        await self.set_data(self.user_id, health=REVIVE_HEALTH, downed_at=None)

    async def increase_death_count(self) -> None:
        if self.get_register_time() is None:
            return
        async with get_session() as session:
            record = await session.get(UserDeathRecord, self.user_id)
            if record is None:
                session.add(UserDeathRecord(user_id=self.user_id, death_count=1))
            else:
                record.death_count += 1
            await session.commit()

    async def get_death_count(self) -> int:
        if self.get_register_time() is None:
            return 0
        async with get_session() as session:
            record = await session.get(UserDeathRecord, self.user_id)
            return record.death_count if record else 0

    @abstractmethod
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
        pass

    async def add_fav(self, count: float) -> None:
        await self.set_data(self.user_id, favorability=self.fav + count)

    async def add_experience(self, count: int) -> None:
        await self.set_data(self.user_id, experience=self.experience + count)

    async def add_vimcoin(self, count: float) -> None:
        await self.set_data(self.user_id, vimcoin=self.vimcoin + count)

    async def use_vimcoin(self, count: float, force: bool = False) -> bool:
        if force or await self.has_vimcoin(count):
            await self.set_data(self.user_id, vimcoin=self.vimcoin - count)
            return True
        return False

    async def has_vimcoin(self, count: float) -> bool:
        return self.vimcoin >= count

    def get_config_key(self, key: str, default: Optional[T] = None) -> T:
        return self.config.get(key, default)

    async def set_config_key(self, key: str, value: Any) -> None:
        self.config[key] = value
        await self.set_data(self.user_id, config=self.config)
