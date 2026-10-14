from dataclasses import dataclass
from random import random  # nosec B311

from nonebot import get_driver
from nonebot_plugin_bag.models import Bag
from nonebot_plugin_items.registry.registry import ResourceLocation
from nonebot_plugin_orm import AsyncSession, get_session
from sqlalchemy import func, select

from .models import EggSelection

# 臭鸡蛋的种类 id：命中后会给目标附着霉运 buff
ROTTEN_EGG_TYPE = "rotten_egg"
# 臭鸡蛋 Ex：命中后爆炸，恶臭持续更久、伤害更高，也有概率在手上爆炸
ROTTEN_EGG_EX_TYPE = "rotten_egg_ex"


@dataclass(frozen=True)
class EggTypeData:
    """一种鸡蛋的属性

    Attributes:
        item_id: 物品 ID
        damage: 每个鸡蛋造成的伤害
        buff_hours: 命中（含反弹、砸自己）后霉运 buff 每层的持续时间；0 表示不附着
        explode_chance: 每个鸡蛋在手上爆炸的概率（爆炸相当于砸自己）
    """

    item_id: str
    damage: float
    buff_hours: int
    explode_chance: float


# 鸡蛋种类注册表：英文 id -> 属性
# 新鸡蛋种类在这里注册后，即可通过 /splat 查看、/splat switch 切换、-t/--type 指定使用
EGG_TYPES: dict[str, EggTypeData] = {
    "egg": EggTypeData(item_id="moonlark:egg", damage=0.2, buff_hours=0, explode_chance=0.0),
    ROTTEN_EGG_TYPE: EggTypeData(item_id="moonlark:rotten_egg", damage=1.0, buff_hours=2, explode_chance=0.01),
    ROTTEN_EGG_EX_TYPE: EggTypeData(item_id="moonlark:rotten_egg_ex", damage=2.0, buff_hours=6, explode_chance=0.03),
}
DEFAULT_EGG_TYPE = "egg"


def get_moonlark_user_ids() -> set[str]:
    """获取 Moonlark 自己的所有账号 ID（砸到这些号会被反弹）"""
    config = get_driver().config
    user_ids: set[str] = {str(value) for value in getattr(config, "bots_list", {}).values() if value}
    # QQ 官方 bot 的 AppID -> QQ 号映射：映射目标是 QQ 号
    user_ids |= {str(value) for value in getattr(config, "bots_appid_map", {}).values() if value}
    master_id = str(getattr(config, "chat_master_user_id", "") or "").strip()
    if master_id:
        user_ids.add(master_id)
    return user_ids


def roll_hand_explosion(egg_type: str, count: int) -> int:
    """计算在手上爆炸的鸡蛋数量（逐个判定爆炸概率，爆炸相当于砸自己）"""
    chance = EGG_TYPES[egg_type].explode_chance
    if chance <= 0 or count <= 0:
        return 0
    return sum(1 for _ in range(count) if random() < chance)


async def get_egg_type_name(egg_type: str, user_id: str) -> str:
    """获取鸡蛋种类的显示名称"""
    from nonebot_plugin_items.utils.get import get_item
    from nonebot_plugin_items.utils.string import get_location_by_id

    location = get_location_by_id(EGG_TYPES[egg_type].item_id)
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
                select(func.coalesce(func.sum(Bag.count), 0)).where(Bag.user_id == user_id, Bag.item_id == item_id)
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
