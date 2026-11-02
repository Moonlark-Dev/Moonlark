from datetime import date
import os
import struct
from typing import Awaitable, Callable, Optional, Tuple

from nonebot_plugin_orm import Model, get_session
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .sql import retry_on_db_conflict


class LuckValue(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    luck_value: Mapped[int]
    generate_date: Mapped[date]
    reroll_count: Mapped[int] = mapped_column(default=0)


# 人品值修正钩子：接收 (user_id, 原始人品值)，返回修正后的人品值
LuckValueHook = Callable[[str, int], Awaitable[int]]
_luck_value_hooks: list[LuckValueHook] = []


def register_luck_value_hook(hook: LuckValueHook) -> None:
    """注册人品值修正钩子

    每次生成或重抽人品值时按注册顺序依次调用，例如 buff 系统可以借此
    在用户带有「霉运」时压低抽到的人品值。
    """
    _luck_value_hooks.append(hook)


async def apply_luck_value_hooks(user_id: str, value: int) -> int:
    """依次应用所有已注册的人品值修正钩子"""
    for hook in _luck_value_hooks:
        value = await hook(user_id, value)
    return value


def _get_june_bias(today: Optional[date] = None) -> int:
    today = today or date.today()
    return 50 if today.month == 6 and 1 <= today.day <= 15 else 0


def _roll_luck_value(bias: int) -> int:
    return struct.unpack("<I", os.urandom(4))[0] % 101 + bias


async def _get_today_luck_value(user_id: str) -> Tuple[int, int]:
    """读取用户今日人品值与已重算次数，必要时生成并写入数据库.

    返回：(人品值, 已重算次数)
    """
    today = date.today()

    # 快路径：今日记录已经存在时直接返回，避免每次读取都去加写锁
    async with get_session() as session:
        value = await session.get(LuckValue, {"user_id": user_id})
        if value is not None and value.generate_date == today:
            return value.luck_value, value.reroll_count

    async def generate_today_value() -> Tuple[int, int]:
        luck_value = await apply_luck_value_hooks(user_id, _roll_luck_value(_get_june_bias(today)))
        async with get_session() as session:
            # 用锁定读把「读取-判断-写入」放在同一个事务里：如果事务期间该行被其它
            # 事务改动，MySQL / MariaDB 会返回 1020（Record has changed since last
            # read in table），而锁定读会让其它写入等待本事务结束。
            value = await session.get(LuckValue, {"user_id": user_id}, with_for_update=True)
            if value is not None and value.generate_date == today:
                return value.luck_value, value.reroll_count
            if value is None:
                session.add(
                    LuckValue(
                        user_id=user_id,
                        luck_value=luck_value,
                        generate_date=today,
                        reroll_count=0,
                    ),
                )
            else:
                value.luck_value = luck_value
                value.generate_date = today
                value.reroll_count = 0
            await session.commit()
            return luck_value, 0

    return await retry_on_db_conflict(generate_today_value)


async def get_luck_value(user_id: str) -> int:
    return (await _get_today_luck_value(user_id))[0]


async def get_luck_value_with_reroll_count(user_id: str) -> Tuple[int, int]:
    """获取用户今日人品值和已重算次数"""
    return await _get_today_luck_value(user_id)


async def reroll_luck_value(user_id: str, max_reroll_count: int) -> Optional[Tuple[int, int]]:
    """
    重新计算今日人品值

    参数:
        user_id: 用户 ID
        max_reroll_count: 最大重算次数

    返回: (新的人品值, 已重算次数) 或 None（如果已达到重算上限或人品值为最大值）

    reroll 规则:
        - 人品值为 0（仅无偏移时）: 50% 留在 0，50% 随机 reroll
        - 人品值在正常范围内: 50% reroll 到更高值，50% reroll 到更低值
        - 人品值达到最大值: 禁止 reroll
    """
    today = date.today()
    bias = _get_june_bias(today)
    max_luck = 100 + bias

    async def reroll() -> Optional[Tuple[int, int]]:
        async with get_session() as session:
            # 重算必须先读现值再写回，用锁定读避免并发写入触发 1020
            value = await session.get(LuckValue, {"user_id": user_id}, with_for_update=True)

            # 如果没有记录或不是今天的记录，先创建今日记录
            if value is None or value.generate_date != today:
                new_luck_value = await apply_luck_value_hooks(user_id, _roll_luck_value(bias))
                if value is None:
                    session.add(
                        LuckValue(
                            user_id=user_id,
                            luck_value=new_luck_value,
                            generate_date=today,
                            reroll_count=0,
                        ),
                    )
                else:
                    value.luck_value = new_luck_value
                    value.generate_date = today
                    value.reroll_count = 0
                await session.commit()
                return new_luck_value, 0

            # 检查是否已达到重算上限
            if value.reroll_count >= max_reroll_count:
                return None

            # 人品值达到最大值时禁止 reroll
            if value.luck_value >= max_luck:
                return None

            current_luck = value.luck_value

            # 根据当前人品值应用不同的 reroll 规则
            if current_luck == 0 and bias == 0:
                # 50% 留在 0，50% 随机 reroll
                if struct.unpack("<I", os.urandom(4))[0] % 2 == 0:
                    new_luck_value = 0
                else:
                    new_luck_value = await apply_luck_value_hooks(user_id, _roll_luck_value(bias))
            else:
                # 50% reroll 到更高值，50% reroll 到更低值
                if struct.unpack("<I", os.urandom(4))[0] % 2 == 0:
                    # reroll 到更高值 (current_luck+1 到 max_luck)
                    new_luck_value = (
                        current_luck + 1 + (struct.unpack("<I", os.urandom(4))[0] % (max_luck - current_luck))
                    )
                else:
                    # reroll 到更低值 (bias 到 current_luck-1)
                    range_size = current_luck - bias
                    if range_size > 1:
                        new_luck_value = bias + struct.unpack("<I", os.urandom(4))[0] % range_size
                    else:
                        new_luck_value = bias
                new_luck_value = await apply_luck_value_hooks(user_id, new_luck_value)

            value.luck_value = new_luck_value
            value.reroll_count += 1

            reroll_count = value.reroll_count

            await session.commit()

            return new_luck_value, reroll_count

    return await retry_on_db_conflict(reroll)
