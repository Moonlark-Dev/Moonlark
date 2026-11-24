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

from typing import Any, Awaitable, Callable
import base64
import inspect
import json
from datetime import datetime, timedelta
from typing import Optional, TypeAlias, TypeGuard, TypeVar
from abc import ABC, abstractmethod
from nonebot_plugin_orm import get_session
from nonebot_plugin_larkuser.exceptions import UserNotRegistered, UserNotWritable
from nonebot_plugin_larkuser.user.lock import user_write_lock
from nonebot_plugin_larkuser.utils.level import get_level_by_experience
from nonebot_plugin_larkuser.models import UserData
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
DOWN_DURATION = timedelta(hours=3)
DOWN_EXPIRE_HEALTH = 1


FAV_LEVELS = [
    (0.005, "stranger"),  # 素昧平生
    (0.050, "acquaintance"),  # 点头之交
    (0.150, "familiar"),  # 熟客
    (0.300, "close_friend"),  # 挚友
    (float("inf"), "cyber_partner"),  # 赛博伴侣
]


class MoonlarkUser(ABC):
    def __init__(self, user_id: str, *, writable: bool = False):
        self.user_id = user_id
        # 只有通过 get_user(user_id, writable=True) 获取的句柄才允许写入用户数值。
        # 普通读取得到的是一份快照，直接拿它做「读 -> 改 -> 写」会在并发时丢失更新，
        # 因此写操作默认被拒绝（见 require_writable / update）。
        self.writable = writable

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

    def is_writable(self) -> bool:
        return self.writable

    def require_writable(self) -> None:
        """校验当前句柄是否被显式标记为可写，否则抛出 :class:`UserNotWritable`"""
        if not self.writable:
            raise UserNotWritable(self.user_id)

    @staticmethod
    def _row_values(row: UserData) -> dict[str, Any]:
        """把数据库行读成普通字典。

        需要在 commit 之前调用：commit 之后 ORM 对象可能过期，异步会话里再访问属性会
        触发隐式 IO（MissingGreenlet）。
        """
        return {
            "nickname": row.nickname,
            "register_time": row.register_time,
            "vimcoin": row.vimcoin,
            "experience": row.experience,
            "health": row.health,
            "downed_at": row.downed_at,
            "fav": row.favorability,
            "config": json.loads(row.config or "{}"),
        }

    def _apply_values(self, values: dict[str, Any]) -> None:
        """用数据库中的最新值刷新内存快照。"""
        self.nickname = values["nickname"]
        self.register_time = values["register_time"]
        self.vimcoin = values["vimcoin"]
        self.experience = values["experience"]
        self.health = values["health"]
        self.downed_at = values["downed_at"]
        self.fav = values["fav"]
        self.config = values["config"]

    async def update(
        self,
        mutator: Callable[[UserData], Awaitable[Any] | Any],
        *,
        require_writable: bool = True,
    ) -> Any:
        """在用户写锁内读取最新数据行、应用 ``mutator`` 并提交。

        同一用户的并发写入会被 ``user_write_lock`` 串行化，且每次修改都基于数据库中的
        最新值，因此 ``add_vimcoin`` / ``use_vimcoin`` 等相对修改不会因为句柄持有的
        旧快照而互相覆盖。

        需要「读取 + 条件写入」原子完成的插件（例如交易前判断余额是否足够），应把整段
        逻辑写在这个回调里，而不是在锁外先读快照、再在锁内写入：

        .. code-block:: python

            user = await get_user(user_id, writable=True)

            async def _pay(row):
                if (row.vimcoin or 0.0) < price:
                    return False
                row.vimcoin -= price
                return True

            if not await user.update(_pay):
                ...

        回调抛出异常时整个修改回滚，不写入数据库。注意锁不可重入：回调里不要再对
        同一用户调用会加锁的写方法（``add_vimcoin`` 等），需要组合操作时在同一个
        回调里直接改 ``row`` 即可。

        :param mutator: 在最新数据行上原地修改字段的回调
        :param require_writable: 是否要求句柄可写（内部维护写，例如零点自动恢复，传 False）
        :return: 回调的返回值
        """
        if require_writable:
            self.require_writable()
        async with user_write_lock(self.user_id):
            async with get_session() as session:
                # with_for_update：多进程部署（共享 MySQL）时也会阻塞其它进程的同一行写入；
                # SQLite 不支持 FOR UPDATE，SQLAlchemy 会自动忽略该子句。
                row = await session.get(UserData, self.user_id, with_for_update=True)
                if row is None:
                    raise UserNotRegistered()
                result = mutator(row)
                if inspect.isawaitable(result):
                    result = await result
                values = self._row_values(row)
                await session.commit()
        self._apply_values(values)
        return result

    def get_nickname(self) -> str:
        return self.nickname or f"匿名-{self.user_id[-4:]}"

    def has_nickname(self) -> bool:
        return bool(self.nickname)

    def get_avatar(self) -> Optional[bytes]:
        return self.avatar

    def get_base64_avatar(self) -> Optional[str]:
        avatar = self.get_avatar()
        if avatar is None:
            return None
        return base64.b64encode(avatar).decode()

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
        """返回倒地剩余时间（最长 DOWN_DURATION），未倒地时返回零时长"""
        if self.downed_at is None:
            return timedelta(0)
        return max(DOWN_DURATION - (datetime.now() - self.downed_at), timedelta(0))

    async def is_down(self) -> bool:
        """是否处于倒地状态。

        已注册用户 HP 为 0 且倒地未超过 DOWN_DURATION（3 小时）时为倒地状态。
        倒地状态最长持续 3 小时，到时将 HP 重置为 DOWN_EXPIRE_HEALTH（1）并自动恢复。
        自动恢复是内部维护写，不要求句柄可写。
        """
        if self.get_register_time() is None or self.get_health() > 0 or self.downed_at is None:
            return False
        if datetime.now() - self.downed_at >= DOWN_DURATION:

            def _expire(row: UserData) -> None:
                # 锁内以数据库状态为准：可能已被别的协程救起或刷新过
                if row.downed_at is not None and datetime.now() - row.downed_at >= DOWN_DURATION:
                    row.health = DOWN_EXPIRE_HEALTH
                    row.downed_at = None

            await self.update(_expire, require_writable=False)
            return False
        return True

    @staticmethod
    def _clamp_health(value: float) -> float:
        return max(0.0, min(float(value), MAX_HEALTH))

    @classmethod
    def _set_health_row(cls, row: UserData, value: float) -> None:
        """把血量写入数据行，并同步 0 HP / 复活时的倒地状态与死亡计数。"""
        value = cls._clamp_health(value)
        current = cls._clamp_health(row.health)
        if value > 0 and row.downed_at is not None:
            row.health = value
            row.downed_at = None
        elif value == 0 and current > 0:
            row.health = 0
            row.downed_at = datetime.now()
            row.death_count = (row.death_count or 0) + 1
        else:
            row.health = value

    async def set_health(self, value: float) -> None:
        """设置血量，限制在 0 ~ MAX_HEALTH。

        血量降到 0 时进入倒地状态并记录一次死亡；血量恢复时清除倒地状态。
        """
        await self.update(lambda row: self._set_health_row(row, value))

    async def heal(self, amount: float) -> None:
        """回复血量，amount 必须为非负数"""
        if amount < 0:
            raise ValueError(f"heal 的血量数值不能为负数：{amount}")

        def _heal(row: UserData) -> None:
            self._set_health_row(row, self._clamp_health(row.health) + amount)

        await self.update(_heal)

    async def damage(self, amount: float) -> bool:
        """扣除血量，amount 必须为非负数。

        血量不足时不会「不进行任何操作」，而是直接将 HP 扣到 0 触发倒地，
        并返回 False（表示未足额扣除）。
        """
        if amount < 0:
            raise ValueError(f"damage 的血量数值不能为负数：{amount}")
        fully_applied = True

        def _damage(row: UserData) -> None:
            nonlocal fully_applied
            current = self._clamp_health(row.health)
            if current < amount:
                fully_applied = False
                self._set_health_row(row, 0)
            else:
                self._set_health_row(row, current - amount)

        await self.update(_damage)
        return fully_applied

    async def revive(self, health: float = REVIVE_HEALTH) -> None:
        """倒地状态结束，将 HP 重置为 health 并清除倒地状态"""
        if self.get_register_time() is None:
            return

        def _revive(row: UserData) -> None:
            row.health = self._clamp_health(health)
            row.downed_at = None

        await self.update(_revive)

    async def increase_death_count(self) -> None:
        if self.get_register_time() is None:
            return

        def _increase(row: UserData) -> None:
            row.death_count = (row.death_count or 0) + 1

        await self.update(_increase)

    async def get_death_count(self) -> int:
        if self.get_register_time() is None:
            return 0
        async with get_session() as session:
            user = await session.get(UserData, self.user_id)
            return user.death_count if user else 0

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
        def _add(row: UserData) -> None:
            row.favorability = (row.favorability or 0.0) + count

        await self.update(_add)

    async def add_experience(self, count: int) -> None:
        def _add(row: UserData) -> None:
            row.experience = (row.experience or 0) + count

        await self.update(_add)

    async def add_vimcoin(self, count: float) -> None:
        def _add(row: UserData) -> None:
            row.vimcoin = (row.vimcoin or 0.0) + count

        await self.update(_add)

    async def use_vimcoin(self, count: float, force: bool = False) -> bool:
        """扣除 VimCoin；余额不足时返回 False（``force=True`` 允许扣成负数）。"""
        spent = False

        def _spend(row: UserData) -> None:
            nonlocal spent
            balance = row.vimcoin or 0.0
            if force or balance >= count:
                row.vimcoin = balance - count
                spent = True

        await self.update(_spend)
        return spent

    async def has_vimcoin(self, count: float) -> bool:
        return self.vimcoin >= count

    def get_config_key(self, key: str, default: Optional[T] = None) -> T:
        return self.config.get(key, default)

    async def set_config_key(self, key: str, value: Any) -> None:
        def _set(row: UserData) -> None:
            config = json.loads(row.config or "{}")
            config[key] = value
            row.config = json.dumps(config)

        await self.update(_set)
