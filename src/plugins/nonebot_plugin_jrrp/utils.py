from asyncio import Lock
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import AsyncGenerator, Literal

from nonebot_plugin_larkuser import MoonlarkUser
from nonebot_plugin_larkutils.jrrp import (
    get_luck_value,
    get_luck_value_with_reroll_count,
    get_max_luck_value,
    reroll_luck_value,
)
from nonebot_plugin_larkutils.sql import retry_on_db_conflict
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .lang import lang
from .models import LuckTrend
from .types import LuckType

_LUCK_TYPE_THRESHOLDS: list[tuple[int, LuckType]] = [
    (101, LuckType.BEYOND_PERFECT),
    (100, LuckType.PERFECT_LUCK),
    (99, LuckType.ALMOST_PERFECT),
    (85, LuckType.GREAT_DAY),
    (71, LuckType.GOOD_DAY),
    (57, LuckType.FAIR_DAY),
    (43, LuckType.AVERAGE_DAY),
    (29, LuckType.BELOW_AVERAGE),
    (15, LuckType.POOR_DAY),
    (1, LuckType.BAD_DAY),
]


def _today() -> date:
    """返回当前 UTC+8 日期."""
    return datetime.now(UTC).astimezone(timezone(timedelta(hours=8))).date()


def get_luck_type(luck_value: int) -> LuckType:
    for threshold, luck_type in _LUCK_TYPE_THRESHOLDS:
        if luck_value >= threshold:
            return luck_type
    return LuckType.TERRIBLE_LUCK


async def get_luck_message(user_id: str) -> str:
    luck_value = await get_luck_value(user_id)
    text = await lang.text(f"message.{get_luck_type(luck_value).name.lower()}", user_id, luck_value)
    # 语言文件里允许某一档不写文案（如 fair_day 聊天不回任何句子），
    # 但渲染卡片失败回退到文本时不能发空消息，至少要把人品值说出来。
    return text if text.strip() else str(luck_value)


async def save_luck_trend(user_id: str, luck_value: int, reroll_count: int = 0) -> None:
    """记录今日人品值到走势表."""
    today = _today()

    async def save() -> None:
        async with get_session() as session:
            # 同一个用户可能同时跑多个 jrrp 指令，先读后写时需要锁定这一行，
            # 否则 MySQL / MariaDB 会因记录在事务期间被改动而返回 1020
            record = await session.get(
                LuckTrend,
                {"user_id": user_id, "record_date": today},
                with_for_update=True,
            )
            if record is None:
                session.add(
                    LuckTrend(
                        user_id=user_id,
                        record_date=today,
                        luck_value=luck_value,
                        reroll_count=reroll_count,
                    ),
                )
            else:
                record.luck_value = luck_value
                record.reroll_count = reroll_count
            await session.commit()

    await retry_on_db_conflict(save)


async def get_luck_trend(
    user_id: str,
    days: int = 7,
) -> list[LuckTrend]:
    """获取用户最近 N 天的人品走势数据."""
    since = _today() - timedelta(days=days - 1)
    async with get_session() as session:
        result = await session.scalars(
            select(LuckTrend)
            .where(LuckTrend.user_id == user_id, LuckTrend.record_date >= since)
            .order_by(LuckTrend.record_date.asc()),
        )
        return list(result.all())


# 同一用户的重算必须串行执行：「读已重算次数 → 计费 → 扣费 → 写回次数」之间有多个
# await，并发时几个协程会基于同一份「第 1 次」快照各自按首档价格扣费，最后写回的
# reroll_count 还会互相覆盖（SQLite 会忽略 with_for_update，单进程内也能复现）。
# 这里用一把按用户回收的锁把整段临界区串行化；跨进程仍由 LuckValue 的
# SELECT ... FOR UPDATE 与 retry_on_db_conflict 兜底。
_reroll_locks: dict[str, Lock] = {}
_reroll_waiters: dict[str, int] = {}


@asynccontextmanager
async def _reroll_lock(user_id: str) -> AsyncGenerator[None, None]:
    lock = _reroll_locks.get(user_id)
    if lock is None:
        lock = _reroll_locks[user_id] = Lock()
    _reroll_waiters[user_id] = _reroll_waiters.get(user_id, 0) + 1
    try:
        async with lock:
            yield
    finally:
        remaining = _reroll_waiters[user_id] - 1
        if remaining > 0:
            _reroll_waiters[user_id] = remaining
        else:
            _reroll_waiters.pop(user_id, None)
            _reroll_locks.pop(user_id, None)


RerollStatus = Literal["ok", "max_reached", "beyond_perfect", "perfect_luck", "insufficient_vimcoin"]


@dataclass(frozen=True)
class RerollOutcome:
    """一次重算的结果，调用方据此决定提示文案。"""

    status: RerollStatus
    luck_value: int = 0
    reroll_count: int = 0
    cost: int = 0
    balance: float = 0.0


async def perform_reroll(
    user: MoonlarkUser,
    user_id: str,
    max_reroll_count: int,
    base_cost: int,
) -> RerollOutcome:
    """在用户级锁内完成「读次数 → 判上限 → 计费 → 扣费 → 重算」。

    费用必须与真正消耗掉的那一次重算对应，所以读次数、扣费、写回次数要在同一个临界区
    里：并发重算才会依次拿到 1/2/3 次和逐档递增的价格，而不是全按首档计费。
    """
    async with _reroll_lock(user_id):
        current_luck, reroll_count = await get_luck_value_with_reroll_count(user_id)

        if reroll_count >= max_reroll_count:
            return RerollOutcome(status="max_reached")

        # 人品值已经到顶时不能再重算。先判上限再扣费，避免扣了钱却没能重算
        if current_luck >= get_max_luck_value():
            return RerollOutcome(status="beyond_perfect" if current_luck > 100 else "perfect_luck")

        cost = base_cost * (reroll_count + 1)

        # 余额检查与扣费在同一次加锁修改里完成，避免并发时白嫖一次重算
        if not await user.use_vimcoin(cost):
            return RerollOutcome(status="insufficient_vimcoin", cost=cost, balance=user.get_vimcoin())

        result = await reroll_luck_value(user_id, max_reroll_count)
        if result is None:
            # 锁内刚检查过次数与上限，正常不会走到这里；真发生了就把钱退回去
            await user.add_vimcoin(cost)
            return RerollOutcome(status="max_reached")

        new_luck, new_reroll_count = result
        return RerollOutcome(
            status="ok",
            luck_value=new_luck,
            reroll_count=new_reroll_count,
            cost=cost,
        )
