"""装备栏的读写与效果接口。

装备从背包中取出（背包数量减一）放入装备槽，每种装备类型同时只能装备一件；
卸下时物品回到背包。装备被动效果（如临时屏障抵挡与反弹）由对应的游戏插件调用
:func:`handle_barrier` 触发。
"""

import json
from datetime import datetime
from random import random  # nosec B311

from nonebot_plugin_bag import get_bag_item
from nonebot_plugin_bag.utils.bag import give_item
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .lang import lang
from .models import Equipped
from .registry import (
    BARRIER_EX_PIERCE_PROBABILITY,
    BARRIER_REFLECT_PROBABILITY,
    TEMP_BARRIER_BLOCKS,
    EquipmentDefinition,
    get_equipment_by_item_id,
    get_equipment_by_type,
)


class BarrierResult:
    """一次屏障判定结果

    Attributes:
        equipped: 用户是否装备着屏障
        blocked: 本次攻击是否被屏障挡下
        reflected: 本次攻击是否被反弹给了攻击者
        pierced: 是否是臭鸡蛋 Ex 击穿了屏障
        remaining: 挡下后剩余的抵挡次数（击穿或未装备时为 None）
        destroyed: 屏障是否在挡下这次攻击后损坏
    """

    def __init__(
        self,
        equipped: bool,
        blocked: bool,
        reflected: bool,
        pierced: bool = False,
        remaining: int | None = None,
        destroyed: bool = False,
    ) -> None:
        self.equipped = equipped
        self.blocked = blocked
        self.reflected = reflected
        self.pierced = pierced
        self.remaining = remaining
        self.destroyed = destroyed


class EquipError(Exception):
    """装备操作失败

    Args:
        code: 失败原因（not_equipment / already_equipped / not_equipped）
        definition: 失败时涉及的装备定义（already_equipped 时为已装备的同类装备）
    """

    def __init__(self, code: str, definition: EquipmentDefinition | None = None) -> None:
        self.code = code
        self.definition = definition
        super().__init__(code)


async def get_equipped_rows(user_id: str) -> list[Equipped]:
    """获取用户装备栏中的全部装备"""
    async with get_session() as session:
        rows = (
            await session.scalars(select(Equipped).where(Equipped.user_id == user_id).order_by(Equipped.time))
        ).all()
        session.expunge_all()
        return list(rows)


async def get_equipped_row(user_id: str, equipment_type: str) -> Equipped | None:
    async with get_session() as session:
        row = await session.scalar(select(Equipped).where(Equipped.user_id == user_id, Equipped.type == equipment_type))
        if row is not None:
            session.expunge(row)
        return row


def _get_state(row: Equipped) -> dict:
    try:
        state = json.loads(row.data)
    except ValueError:
        return {}
    return state if isinstance(state, dict) else {}


async def equip_from_bag(user_id: str, bag_index: int) -> EquipmentDefinition:
    """将背包指定序号的物品装备到装备栏。

    Raises:
        IndexError: 背包中找不到该序号物品
        EquipError: 该物品不是装备，或该类型的装备已经装备了一件
    """
    item = await get_bag_item(user_id, bag_index)
    definition = get_equipment_by_item_id(str(item.stack.item.getLocation()))
    await item.unlock_item()
    if definition is None:
        raise EquipError("not_equipment")
    if await get_equipped_row(user_id, definition.type) is not None:
        raise EquipError("already_equipped", definition)

    item.stack.count -= 1
    await item.on_delete()
    async with get_session() as session:
        session.add(
            Equipped(
                user_id=user_id,
                type=definition.type,
                item_id=definition.item_id,
                data=json.dumps(definition.state_keys),
                time=datetime.now(),
            ),
        )
        await session.commit()
    return definition


async def unequip(user_id: str, equipment_type: str) -> EquipmentDefinition:
    """卸下指定类型的装备，物品回到背包。

    Raises:
        EquipError: 该类型没有装备中的装备
    """
    row = await get_equipped_row(user_id, equipment_type)
    if row is None:
        raise EquipError("not_equipped")

    from nonebot_plugin_items.utils.get import get_item
    from nonebot_plugin_items.utils.string import get_location_by_id

    stack = await get_item(get_location_by_id(row.item_id), user_id, 1)
    await give_item(user_id, stack)
    async with get_session() as session:
        db_row = await session.get(Equipped, row.id_)
        if db_row is not None:
            await session.delete(db_row)
        await session.commit()
    return get_equipment_by_type(equipment_type) or get_equipment_by_item_id(row.item_id)


async def build_state_text(definition: EquipmentDefinition, row: Equipped, user_id: str) -> str:
    """构建装备的动态状态文本（如屏障的剩余抵挡次数）"""
    state = _get_state(row)
    if definition.type == "temp_barrier":
        return await lang.text("state.blocks", user_id, state.get("blocks", TEMP_BARRIER_BLOCKS))
    return ""


async def handle_barrier(user_id: str, is_rotten_egg_ex: bool) -> "BarrierResult":
    """处理鸡蛋打到装备了临时屏障的用户。

    屏障不存在时返回 ``equipped=False``；臭鸡蛋 Ex 有 80% 概率击穿屏障（不消耗抵挡次数）。
    每次成功抵挡消耗 1 点抵挡次数，抵挡时有 2% 概率把攻击反弹给攻击者，次数归零后屏障损坏消失。
    """
    row = await get_equipped_row(user_id, "temp_barrier")
    if row is None:
        return BarrierResult(equipped=False, blocked=False, reflected=False)
    if is_rotten_egg_ex and random() < BARRIER_EX_PIERCE_PROBABILITY:  # nosec B311
        return BarrierResult(equipped=True, blocked=False, reflected=False, pierced=True)

    state = _get_state(row)
    remaining = state.get("blocks", TEMP_BARRIER_BLOCKS) - 1
    reflected = random() < BARRIER_REFLECT_PROBABILITY  # nosec B311
    async with get_session() as session:
        db_row = await session.get(Equipped, row.id_)
        if db_row is None:
            return BarrierResult(equipped=False, blocked=False, reflected=False)
        if remaining <= 0:
            await session.delete(db_row)
        else:
            db_row.data = json.dumps({**state, "blocks": remaining})
        await session.commit()
    return BarrierResult(
        equipped=True,
        blocked=True,
        reflected=reflected,
        remaining=max(remaining, 0),
        destroyed=remaining <= 0,
    )
