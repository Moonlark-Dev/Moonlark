from datetime import timedelta

import pytest


class _FakeUser:
    """模拟 larkuser 中只有 VimCoin 交互的用户"""

    def __init__(self, vimcoin: float = 1000.0) -> None:
        self.vimcoin = vimcoin

    async def has_vimcoin(self, count: float) -> bool:
        return self.vimcoin >= count

    async def use_vimcoin(self, count: float) -> bool:
        if not await self.has_vimcoin(count):
            return False
        self.vimcoin -= count
        return True

    async def add_vimcoin(self, count: float) -> None:
        self.vimcoin += count

    def get_vimcoin(self) -> float:
        return self.vimcoin


@pytest.fixture
def fake_user(monkeypatch: pytest.MonkeyPatch) -> _FakeUser:
    import nonebot_plugin_larkuser

    user = _FakeUser()

    async def fake_get_user(_user_id: str):
        return user

    monkeypatch.setattr(nonebot_plugin_larkuser, "get_user", fake_get_user)
    return user


@pytest.mark.asyncio
async def test_recipes_and_levels() -> None:
    from nonebot_plugin_craft.recipes import LEVEL_SLOTS, MAX_LEVEL, RECIPES

    assert LEVEL_SLOTS == {1: 2, 2: 4, 3: 6, 4: 10}
    assert MAX_LEVEL == 4
    assert RECIPES["rotten_egg"].inputs == {"moonlark:egg": 1}
    assert RECIPES["rotten_egg"].vimcoin == 10
    assert RECIPES["rotten_egg"].duration == timedelta(hours=6)
    assert RECIPES["rotten_egg"].output_id == "moonlark:rotten_egg"
    assert RECIPES["rotten_egg_ex"].duration == timedelta(hours=3)
    assert RECIPES["cake"].inputs == {"moonlark:egg": 5, "moonlark:milk": 3}
    assert RECIPES["cake"].duration == timedelta(hours=24)


@pytest.mark.asyncio
async def test_machine_default_and_slots() -> None:
    from nonebot_plugin_craft.utils import get_machine, get_slots_info

    machine = await get_machine("crafter1")
    assert machine.level == 1
    total, used = await get_slots_info("crafter1")
    assert (total, used) == (2, 0)


@pytest.mark.asyncio
async def test_start_job_deducts_materials_and_slots(fake_user: _FakeUser) -> None:
    from nonebot_plugin_orm import get_session

    from nonebot_plugin_bag.models import Bag
    from nonebot_plugin_craft.recipes import RECIPES
    from nonebot_plugin_craft.utils import get_slots_info, start_job

    async def add_bag(user_id: str, item_id: str, count: int) -> None:
        async with get_session() as session:
            session.add(Bag(user_id=user_id, item_id=item_id, count=count, bag_index=1, data="{}", locked=False))
            await session.commit()

    # 材料不足时不扣 VimCoin，也不创建任务
    with pytest.raises(Exception):
        await start_job("crafter2", RECIPES["rotten_egg"])
    assert fake_user.vimcoin == 1000.0

    await add_bag("crafter2", "moonlark:egg", 3)
    job = await start_job("crafter2", RECIPES["rotten_egg"])
    assert job.recipe_id == "rotten_egg"
    # 1 个鸡蛋 + 10 VimCoin
    assert fake_user.vimcoin == 990.0
    total, used = await get_slots_info("crafter2")
    assert used == 1
    assert total == 2


@pytest.mark.asyncio
async def test_start_job_slot_limit(fake_user: _FakeUser) -> None:
    from nonebot_plugin_orm import get_session
    from sqlalchemy import select, func

    from nonebot_plugin_bag.models import Bag
    from nonebot_plugin_craft.recipes import RECIPES
    from nonebot_plugin_craft.models import CraftingJob
    from nonebot_plugin_craft.utils import NoFreeSlot, get_slots_info, start_job

    async with get_session() as session:
        session.add(
            Bag(
                user_id="crafter3",
                item_id="moonlark:egg",
                count=10,
                bag_index=1,
                data="{}",
                locked=False,
            )
        )
        await session.commit()

    # 等级 1 只有 2 个槽位
    await start_job("crafter3", RECIPES["rotten_egg"])
    await start_job("crafter3", RECIPES["rotten_egg"])
    with pytest.raises(NoFreeSlot):
        await start_job("crafter3", RECIPES["rotten_egg"])
    total, used = await get_slots_info("crafter3")
    assert (total, used) == (2, 2)
    async with get_session() as session:
        count = await session.scalar(
            select(func.count()).select_from(CraftingJob).where(CraftingJob.user_id == "crafter3")
        )
        assert count == 2


@pytest.mark.asyncio
async def test_collect_finished_jobs_delivers_output(fake_user: _FakeUser) -> None:
    from datetime import datetime

    from nonebot_plugin_orm import get_session
    from sqlalchemy import select

    from nonebot_plugin_bag.models import Bag
    from nonebot_plugin_craft.models import CraftingJob
    from nonebot_plugin_craft.recipes import RECIPES

    from nonebot_plugin_craft.utils import collect_finished_jobs, start_job

    async with get_session() as session:
        session.add(
            Bag(
                user_id="crafter4",
                item_id="moonlark:egg",
                count=5,
                bag_index=1,
                data="{}",
                locked=False,
            )
        )
        await session.commit()

    job = await start_job("crafter4", RECIPES["rotten_egg"])

    # 还没到时间，不能领取
    assert await collect_finished_jobs("crafter4") == []

    # 时间到点后可领取，产物发给用户
    async with get_session() as session:
        row = await session.get(CraftingJob, job.id_)
        row.finish_time = datetime.now() - timedelta(minutes=1)
        await session.commit()

    deliveries = await collect_finished_jobs("crafter4")
    assert deliveries == [(RECIPES["rotten_egg"], 1)]

    async with get_session() as session:
        rotten = (
            await session.scalars(select(Bag).where(Bag.user_id == "crafter4", Bag.item_id == "moonlark:rotten_egg"))
        ).all()
        assert sum(row.count for row in rotten) == 1


@pytest.mark.asyncio
async def test_upgrade_costs(fake_user: _FakeUser) -> None:
    from nonebot_plugin_craft.recipes import LEVEL_SLOTS
    from nonebot_plugin_craft.utils import get_machine, get_upgrade_cost, try_upgrade

    assert get_upgrade_cost(1) == 300
    assert get_upgrade_cost(4) is None

    level, cost, slots = await try_upgrade("upgrader1")
    assert (level, cost, slots) == (2, 300, LEVEL_SLOTS[2])
    assert fake_user.vimcoin == 700.0
    machine = await get_machine("upgrader1")
    assert machine.level == 2

    # 再次升级时 VimCoin 不足会抛异常
    from nonebot_plugin_craft.utils import NotEnoughVimcoin

    fake_user.vimcoin = 100.0
    with pytest.raises(NotEnoughVimcoin):
        await try_upgrade("upgrader1")
