from nonebot_plugin_bag.models import Bag
from nonebot_plugin_items.registry.registry import ResourceLocation
from nonebot_plugin_orm import AsyncSession, get_session
from sqlalchemy import func, select


class NotEnoughEggs(Exception):
    def __init__(self, need: int, have: int) -> None:
        self.need = need
        self.have = have


async def get_egg_count(user_id: str, location: ResourceLocation) -> int:
    item_id = str(location)
    async with get_session() as session:
        return (
            await session.scalar(
                select(func.coalesce(func.sum(Bag.count), 0)).where(Bag.user_id == user_id, Bag.item_id == item_id),
            )
        ) or 0


async def deduct_eggs(session: AsyncSession, user_id: str, location: ResourceLocation, count: int) -> None:
    """在给定会话（事务）中扣除指定数量的鸡蛋，不足时抛出 NotEnoughEggs"""
    item_id = str(location)
    rows = (
        (
            await session.execute(
                select(Bag).where(Bag.user_id == user_id, Bag.item_id == item_id).order_by(Bag.bag_index),
            )
        )
        .scalars()
        .all()
    )
    total = sum(row.count for row in rows)
    if total < count:
        raise NotEnoughEggs(count, total)
    remaining = count
    for row in rows:
        if remaining <= 0:
            break
        amount = min(remaining, row.count)
        row.count -= amount
        remaining -= amount
        if row.count <= 0:
            await session.delete(row)
