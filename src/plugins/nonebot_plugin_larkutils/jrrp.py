from datetime import date
import os
import struct
from typing import Optional, Tuple
from nonebot_plugin_orm import Model, get_session
from sqlalchemy import String
from sqlalchemy.orm import mapped_column, Mapped


class LuckValue(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    luck_value: Mapped[int]
    generate_date: Mapped[date]
    reroll_count: Mapped[int] = mapped_column(default=0)


async def get_luck_value(user_id: str) -> int:
    async with get_session() as session:
        value = await session.get(LuckValue, {"user_id": user_id})
        if value is not None and value.generate_date == date.today():
            return value.luck_value
        value = LuckValue(
            user_id=user_id,
            luck_value=(luck_value := struct.unpack("<I", os.urandom(4))[0] % 101),
            generate_date=date.today(),
            reroll_count=0,
        )
        await session.merge(value)
        await session.commit()
    return luck_value


async def get_luck_value_with_reroll_count(user_id: str) -> Tuple[int, int]:
    """获取用户今日人品值和已重算次数"""
    async with get_session() as session:
        value = await session.get(LuckValue, {"user_id": user_id})
        if value is not None and value.generate_date == date.today():
            return value.luck_value, value.reroll_count
        luck_value = struct.unpack("<I", os.urandom(4))[0] % 101
        value = LuckValue(
            user_id=user_id,
            luck_value=luck_value,
            generate_date=date.today(),
            reroll_count=0,
        )
        await session.merge(value)
        await session.commit()
        return luck_value, 0


async def reroll_luck_value(user_id: str, max_reroll_count: int) -> Optional[Tuple[int, int]]:
    """
    重新计算今日人品值

    参数:
        user_id: 用户 ID
        max_reroll_count: 最大重算次数

    返回: (新的人品值, 已重算次数) 或 None（如果已达到重算上限或人品值为100）

    reroll 规则:
        - 人品值为 0: 50% 留在 0，50% 随机 reroll
        - 人品值为 1-99: 50% reroll 到更高值，50% reroll 到更低值
        - 人品值为 100: 禁止 reroll
    """
    async with get_session() as session:
        value = await session.get(LuckValue, {"user_id": user_id})

        # 如果没有记录或不是今天的记录，先创建今日记录
        if value is None or value.generate_date != date.today():
            new_luck_value = struct.unpack("<I", os.urandom(4))[0] % 101
            value = LuckValue(
                user_id=user_id,
                luck_value=new_luck_value,
                generate_date=date.today(),
                reroll_count=0,
            )
            await session.merge(value)
            await session.commit()
            return new_luck_value, 0

        # 检查是否已达到重算上限
        if value.reroll_count >= max_reroll_count:
            return None

        # 人品值为 100 时禁止 reroll
        if value.luck_value == 100:
            return None

        current_luck = value.luck_value

        # 根据当前人品值应用不同的 reroll 规则
        if current_luck == 0:
            # 50% 留在 0，50% 随机 reroll
            if struct.unpack("<I", os.urandom(4))[0] % 2 == 0:
                new_luck_value = 0
            else:
                new_luck_value = struct.unpack("<I", os.urandom(4))[0] % 101
        elif 1 <= current_luck <= 99:
            # 50% reroll 到更高值，50% reroll 到更低值
            if struct.unpack("<I", os.urandom(4))[0] % 2 == 0:
                # reroll 到更高值 (current_luck+1 到 100)
                new_luck_value = current_luck + 1 + (struct.unpack("<I", os.urandom(4))[0] % (100 - current_luck))
            else:
                # reroll 到更低值 (0 到 current_luck-1)
                if current_luck > 1:
                    new_luck_value = struct.unpack("<I", os.urandom(4))[0] % current_luck
                else:
                    new_luck_value = 0

        value.luck_value = new_luck_value
        value.reroll_count += 1

        reroll_count = value.reroll_count

        await session.merge(value)
        await session.commit()

        return new_luck_value, reroll_count
