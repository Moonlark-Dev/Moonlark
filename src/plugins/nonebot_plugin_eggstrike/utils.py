from nonebot_plugin_bag.models import Bag
from nonebot_plugin_items.registry.registry import ResourceLocation
from nonebot_plugin_orm import AsyncSession, get_session
from sqlalchemy import func, select

from .models import EggSelection

# 鸡蛋种类注册表：英文 id -> (物品 ID, 每个鸡蛋造成的伤害)
# 新鸡蛋种类在这里注册后，即可通过 /splat 查看、/splat switch 切换、-t/--type 指定使用
EGG_TYPES: dict[str, tuple[str, float]] = {
    "egg": ("moonlark:egg", 0.2),
    "rotten_egg": ("moonlark:rotten_egg", 1.0),
}
DEFAULT_EGG_TYPE = "egg"


async def get_egg_type_name(egg_type: str, user_id: str) -> str:
    """获取鸡蛋种类的显示名称"""
    from nonebot_plugin_items.utils.get import get_item
    from nonebot_plugin_items.utils.string import get_location_by_id

    location = get_location_by_id(EGG_TYPES[egg_type][0])
    stack = await get_item(location, user_id)
    return await stack.getName()


def resolve_egg_type(value: str) -> str | None:
    """将数字（1 起）或英文 id 解析为鸡蛋种类，无效返回 None"""
    if value.isdigit():
        keys = list(EGG_TYPES)
        index = int(value)
        if 1 <= index <= len(keys):
            return keys[index - 1]
        return None
    return value if value in EGG_TYPES else None


async def get_selected_egg_type(user_id: str) -> str:
    """获取用户保存的默认鸡蛋种类，未设置或已失效时回退到默认鸡蛋"""
    async with get_session() as session:
        row = await session.get(EggSelection, user_id)
        if row is None or row.egg_id not in EGG_TYPES:
            return DEFAULT_EGG_TYPE
        return row.egg_id


async def set_selected_egg_type(user_id: str, egg_type: str) -> None:
    """保存用户的默认鸡蛋种类"""
    async with get_session() as session:
        row = await session.get(EggSelection, user_id)
        if row is None:
            session.add(EggSelection(user_id=user_id, egg_id=egg_type))
        else:
            row.egg_id = egg_type
        await session.commit()


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
