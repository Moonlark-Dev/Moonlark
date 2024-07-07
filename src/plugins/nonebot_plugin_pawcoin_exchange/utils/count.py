from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..models import Exchanged


async def add_exchanged_count(user_id: str, count: int, vimcoin: float) -> None:
    async with get_session() as session:
        exchange = await session.get(Exchanged, {"user_id": user_id})
        if exchange is None:
            exchange = Exchanged(user_id=user_id, pawcoin=0, vimcoin=0.0)
        exchange.pawcoin += count
        exchange.vimcoin += vimcoin
        await session.merge(exchange)
        await session.commit()


async def get_exchanged_pawcoin() -> int:
    count = 0
    async with get_session() as session:
        for c in await session.scalars(select(Exchanged.pawcoin)):
            count += c
    return count
