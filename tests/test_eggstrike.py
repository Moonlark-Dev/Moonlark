from datetime import datetime, timedelta

import pytest


@pytest.mark.asyncio
async def test_get_start_datetime() -> None:
    from nonebot_plugin_eggstrike.__main__ import get_start_datetime

    assert get_start_datetime("7d") is not None
    assert get_start_datetime("30d") is not None
    assert get_start_datetime("total") is None


@pytest.mark.asyncio
async def test_attack_record_queries() -> None:
    from nonebot_plugin_eggstrike.__main__ import build_ranking, get_start_datetime, max_count, sum_count
    from nonebot_plugin_eggstrike.models import AttackRecord
    from nonebot_plugin_orm import get_session

    now = datetime.now()
    async with get_session() as session:
        session.add(AttackRecord(user_id="u1", target_id="t1", count=5, egg_id="moonlark:egg", time=now))
        session.add(
            AttackRecord(user_id="u1", target_id="t1", count=3, egg_id="moonlark:egg", time=now - timedelta(days=10)),
        )
        session.add(AttackRecord(user_id="u2", target_id="t1", count=2, egg_id="moonlark:egg", time=now))
        session.add(AttackRecord(user_id="u2", target_id="t2", count=8, egg_id="moonlark:egg", time=now))
        await session.commit()

    assert await sum_count(AttackRecord.target_id, "t1", get_start_datetime("7d")) == 7
    assert await sum_count(AttackRecord.target_id, "t1", None) == 10
    assert await sum_count(AttackRecord.user_id, "u2", None) == 10
    assert await max_count(AttackRecord.user_id, "u1", None) == 5
    assert await max_count(AttackRecord.target_id, "t2", None) == 8

    rows = await build_ranking(AttackRecord.target_id, "total")
    assert rows[0].target_id == "t1"
    assert rows[0].total_count == 10

    rows = await build_ranking(AttackRecord.user_id, "7d")
    assert rows[0].user_id == "u2"
    assert rows[0].total_count == 10


@pytest.mark.asyncio
async def test_egg_item_properties() -> None:
    from nonebot_plugin_items.registry import ITEMS
    from nonebot_plugin_items.registry.registry import ResourceLocation

    location = ResourceLocation("moonlark", "egg")
    egg = ITEMS.getValue(location)
    assert egg.getProperties()["star"] == 1
    assert egg.getProperties()["useable"] is False


@pytest.mark.asyncio
async def test_shop_goods_contains_egg() -> None:
    from nonebot_plugin_shop.goods import GOODS

    assert any(item_id == "moonlark:egg" for item_id, _ in GOODS)


@pytest.mark.asyncio
async def test_consume_eggs() -> None:
    from nonebot_plugin_bag.models import Bag
    from nonebot_plugin_items.utils.string import get_location_by_id
    from nonebot_plugin_orm import get_session

    from nonebot_plugin_eggstrike.utils import NotEnoughEggs, deduct_eggs, get_egg_count

    async with get_session() as session:
        session.add(Bag(user_id="consumer1", item_id="moonlark:egg", count=10, bag_index=1, data="{}", locked=False))
        session.add(Bag(user_id="consumer1", item_id="moonlark:egg", count=5, bag_index=2, data="{}", locked=False))
        await session.commit()

    egg_location = get_location_by_id("moonlark:egg")
    assert await get_egg_count("consumer1", egg_location) == 15
    async with get_session() as session:
        await deduct_eggs(session, "consumer1", egg_location, 12)
        await session.commit()
    assert await get_egg_count("consumer1", egg_location) == 3
    with pytest.raises(NotEnoughEggs):
        async with get_session() as session:
            await deduct_eggs(session, "consumer1", egg_location, 100)
    assert await get_egg_count("consumer1", egg_location) == 3


@pytest.mark.asyncio
async def test_deduct_eggs_rolls_back_partial_on_shortage() -> None:
    from nonebot_plugin_bag.models import Bag
    from nonebot_plugin_items.utils.string import get_location_by_id
    from nonebot_plugin_orm import get_session

    from nonebot_plugin_eggstrike.utils import NotEnoughEggs, deduct_eggs, get_egg_count

    async with get_session() as session:
        session.add(Bag(user_id="consumer2", item_id="moonlark:egg", count=7, bag_index=1, data="{}", locked=False))
        await session.commit()

    egg_location = get_location_by_id("moonlark:egg")
    with pytest.raises(NotEnoughEggs):
        async with get_session() as session:
            await deduct_eggs(session, "consumer2", egg_location, 10)
    assert await get_egg_count("consumer2", egg_location) == 7
