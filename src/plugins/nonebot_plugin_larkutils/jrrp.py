from datetime import date
import os
import struct
from nonebot_plugin_orm import Model, get_session
from sqlalchemy import String
from sqlalchemy.orm import mapped_column, Mapped


class LuckValue(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    luck_value: Mapped[int]
    generate_date: Mapped[date]


async def get_luck_value(user_id: str) -> int:
    async with get_session() as session:
        value = await session.get(LuckValue, {"user_id": user_id})
        if value is not None and value.generate_date == date.today():
            return value.luck_value
        value = LuckValue(
            user_id=user_id, luck_value=(luck_value := struct.unpack("<I",os.urandom(4))[0] % 101), generate_date=date.today()
        )
        await session.merge(value)
        await session.commit()
    return luck_value
