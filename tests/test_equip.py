import json

import pytest


@pytest.mark.asyncio
async def test_barrier_registry() -> None:
    from nonebot_plugin_equip.registry import (
        BARRIER_EX_PIERCE_PROBABILITY,
        BARRIER_REFLECT_PROBABILITY,
        TEMP_BARRIER_BLOCKS,
        EQUIPMENTS,
        get_equipment_by_item_id,
        get_equipment_by_type,
    )

    definition = get_equipment_by_item_id("moonlark:temp_barrier")
    assert definition is not None and definition.type == "temp_barrier"
    assert get_equipment_by_type("temp_barrier") is definition
    assert definition.state_keys == {"blocks": TEMP_BARRIER_BLOCKS}
    assert definition in EQUIPMENTS.values()
    assert 0 < BARRIER_REFLECT_PROBABILITY < 1
    assert 0 < BARRIER_EX_PIERCE_PROBABILITY < 1
    assert TEMP_BARRIER_BLOCKS == 20


@pytest.mark.asyncio
async def test_handle_barrier_block_and_destroy(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime

    from nonebot_plugin_orm import get_session
    from sqlalchemy import select

    import nonebot_plugin_equip.api as api
    from nonebot_plugin_equip.models import Equipped
    from nonebot_plugin_equip.registry import TEMP_BARRIER_BLOCKS

    # 没有装备屏障：直接穿透
    result = await api.handle_barrier("no-barrier", is_rotten_egg_ex=False)
    assert not result.blocked and not result.reflected

    user_id = "barrier-user"
    async with get_session() as session:
        session.add(
            Equipped(
                user_id=user_id,
                type="temp_barrier",
                item_id="moonlark:temp_barrier",
                data=json.dumps({"blocks": 1}),
                time=datetime.now(),
            ),
        )
        await session.commit()

    # 最后一层：挡下后屏障损坏
    result = await api.handle_barrier(user_id, is_rotten_egg_ex=False)
    assert result.blocked and not result.reflected
    assert result.destroyed and result.remaining == 0
    async with get_session() as session:
        rows = (await session.scalars(select(Equipped).where(Equipped.user_id == user_id))).all()
        assert not rows


@pytest.mark.asyncio
async def test_handle_barrier_reflect(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime

    from nonebot_plugin_orm import get_session
    from sqlalchemy import select

    import nonebot_plugin_equip.api as api
    from nonebot_plugin_equip.models import Equipped

    user_id = "barrier-reflect"
    async with get_session() as session:
        session.add(
            Equipped(
                user_id=user_id,
                type="temp_barrier",
                item_id="moonlark:temp_barrier",
                data=json.dumps({"blocks": 20}),
                time=datetime.now(),
            ),
        )
        await session.commit()

    # random() 让 2% 反弹概率一定触发
    monkeypatch.setattr(api, "random", lambda: 0.0)
    result = await api.handle_barrier(user_id, is_rotten_egg_ex=False)
    assert result.blocked and result.reflected
    assert result.remaining == 19

    # 屏障不存在时不拦截
    result = await api.handle_barrier("barrier-reflect-none", is_rotten_egg_ex=False)
    assert not result.blocked


@pytest.mark.asyncio
async def test_handle_barrier_ex_pierce(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime

    from nonebot_plugin_orm import get_session

    import nonebot_plugin_equip.api as api
    from nonebot_plugin_equip.models import Equipped

    user_id = "barrier-pierce"
    async with get_session() as session:
        session.add(
            Equipped(
                user_id=user_id,
                type="temp_barrier",
                item_id="moonlark:temp_barrier",
                data=json.dumps({"blocks": 20}),
                time=datetime.now(),
            ),
        )
        await session.commit()

    # random() < 0.8：臭鸡蛋 Ex 击穿屏障，不消耗抵挡次数
    monkeypatch.setattr(api, "random", lambda: 0.0)
    result = await api.handle_barrier(user_id, is_rotten_egg_ex=True)
    assert result.equipped and not result.blocked and result.pierced
    assert result.remaining is None

    # random() >= 0.8：臭鸡蛋 Ex 也被挡下
    monkeypatch.setattr(api, "random", lambda: 0.99)
    result = await api.handle_barrier(user_id, is_rotten_egg_ex=True)
    assert result.blocked and result.remaining == 19


@pytest.mark.asyncio
async def test_equip_from_bag_and_unequip() -> None:
    from nonebot_plugin_orm import get_session
    from sqlalchemy import select

    from nonebot_plugin_bag.models import Bag
    from nonebot_plugin_equip.api import EquipError, equip_from_bag, get_equipped_rows, unequip

    user_id = "equip-user"
    async with get_session() as session:
        session.add(
            Bag(
                user_id=user_id,
                item_id="moonlark:temp_barrier",
                count=2,
                bag_index=1,
                data="{}",
                locked=False,
            )
        )
        await session.commit()

    definition = await equip_from_bag(user_id, 1)
    assert definition.type == "temp_barrier"

    # 背包数量 +1，装备栏 +1
    rows = await get_equipped_rows(user_id)
    assert len(rows) == 1
    async with get_session() as session:
        bag_item = await session.scalar(select(Bag).where(Bag.user_id == user_id, Bag.bag_index == 1))
        assert bag_item.count == 1

    # 无法同时装备两件同类型
    with pytest.raises(EquipError):
        await equip_from_bag(user_id, 1)  # 通过 index=1 找到同一件装备（数量 +1 后仍存在）

    await unequip(user_id, "temp_barrier")
    assert await get_equipped_rows(user_id) == []
    async with get_session() as session:
        bag_items = (await session.scalars(select(Bag).where(Bag.user_id == user_id))).all()
        assert sum(row.count for row in bag_items) == 2

    # 没有装备时卸下会失败
    with pytest.raises(EquipError):
        await unequip(user_id, "temp_barrier")
