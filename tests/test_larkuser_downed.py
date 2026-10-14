"""倒地（down）机制与救起（rescue）逻辑的回归测试。

覆盖：

- 倒地最长持续 3 小时（DOWN_DURATION），到期后自动恢复为 1 HP（DOWN_EXPIRE_HEALTH）；
- :func:`process_rescue` 的各种结果（成功 / 目标未倒地 / 救人者余额不足 /
  被救者余额不足），以及支付方对应的 VimCoin 扣除；
- health_recovery 定时任务对超过倒地时长的用户按 1 HP 自动恢复。
"""

from datetime import datetime, timedelta
import importlib

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def user_db(monkeypatch):
    """建立 UserData / LastSeenRecord 的内存数据库，并把相关 get_session 指向它"""
    from nonebot_plugin_larkuser.models import UserData
    from nonebot_plugin_larkutils.models import MainAccountMapping
    from nonebot_plugin_last_seen.models import LastSeenRecord

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(UserData.__table__.create)
        await conn.run_sync(LastSeenRecord.__table__.create)
        await conn.run_sync(MainAccountMapping.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    targets = (
        "nonebot_plugin_larkuser.user.registered",
        "nonebot_plugin_larkuser.user.base",
        "nonebot_plugin_last_seen.__main__",
        "nonebot_plugin_health_recovery.__main__",
        "nonebot_plugin_larkutils.subaccount",
    )
    for module_path in targets:
        monkeypatch.setattr(importlib.import_module(module_path), "get_session", lambda **_: factory())

    async def add_user(
        user_id: str,
        vimcoin: float = 0.0,
        health: float = 100.0,
        downed_at: datetime | None = None,
    ) -> None:
        async with factory() as session:
            session.add(
                UserData(user_id=user_id, nickname="", register_time=datetime.now(), vimcoin=vimcoin, health=health)
            )
            await session.flush()
            if downed_at is not None:
                user = await session.get(UserData, {"user_id": user_id})
                user.downed_at = downed_at
            await session.commit()

    yield factory, add_user
    await engine.dispose()


async def _load(factory, user_id: str):
    from nonebot_plugin_larkuser.models import UserData

    async with factory() as session:
        return await session.get(UserData, {"user_id": user_id})


async def _make_user(user_id: str):
    from nonebot_plugin_larkuser.user.registered import MoonlarkRegisteredUser

    user = MoonlarkRegisteredUser(user_id)
    await user.setup_user()
    return user


# ------------------------------------------------------------------ 倒地时长 --


@pytest.mark.asyncio
async def test_down_expires_after_three_hours(user_db):
    """倒地 3 小时后不再是倒地状态，HP 自动恢复为 1 并清除倒地时间"""
    from nonebot_plugin_larkuser.user.base import DOWN_EXPIRE_HEALTH

    factory, add_user = user_db
    await add_user("10001", health=0, downed_at=datetime.now() - timedelta(hours=3, minutes=1))

    user = await _make_user("10001")
    assert await user.is_down() is False
    assert user.get_health() == DOWN_EXPIRE_HEALTH
    assert user.downed_at is None

    row = await _load(factory, "10001")
    assert row.health == DOWN_EXPIRE_HEALTH
    assert row.downed_at is None


@pytest.mark.asyncio
async def test_down_duration_is_three_hours():
    """倒地时长常量应为 3 小时"""
    from nonebot_plugin_larkuser.user.base import DOWN_DURATION

    assert DOWN_DURATION == timedelta(hours=3)


@pytest.mark.asyncio
async def test_down_within_duration_stays_downed(user_db):
    """倒地未满 3 小时时仍是倒地状态，且剩余时间正确，接近 2 小时"""
    factory, add_user = user_db
    downed_at = datetime.now() - timedelta(hours=1)
    await add_user("10001", health=0, downed_at=downed_at)

    user = await _make_user("10001")
    assert await user.is_down() is True
    remaining = user.get_down_remaining()
    assert timedelta(hours=1, minutes=59, seconds=50) < remaining <= timedelta(hours=2)


@pytest.mark.asyncio
async def test_health_recovery_revives_expired_down_to_one(user_db):
    """定时任务应把倒地超过 3 小时的用户恢复为 1 HP，未到时不恢复"""
    from nonebot_plugin_health_recovery.__main__ import recover_health

    factory, add_user = user_db
    await add_user("expired", health=0, downed_at=datetime.now() - timedelta(hours=4))
    await add_user("fresh", health=0, downed_at=datetime.now() - timedelta(hours=1))

    await recover_health()

    assert (await _load(factory, "expired")).health == 1
    assert (await _load(factory, "expired")).downed_at is None
    assert (await _load(factory, "fresh")).health == 0
    assert (await _load(factory, "fresh")).downed_at is not None


# -------------------------------------------------------------------- 救起 --


@pytest.mark.asyncio
async def test_rescue_success_paid_by_rescuer(user_db):
    """由救人者支付费用：扣除救人者 50 vi，被救者恢复 5 HP"""
    from nonebot_plugin_larkuser.user.base import REVIVE_HEALTH
    from nonebot_plugin_larkuser.utils.downed import RescueResult, process_rescue

    factory, add_user = user_db
    await add_user("rescuer", vimcoin=100)
    await add_user("downed", vimcoin=10, health=0, downed_at=datetime.now() - timedelta(minutes=10))

    rescuer = await _make_user("rescuer")
    downed_user = await _make_user("downed")
    result = await process_rescue(rescuer, downed_user, pay_by_rescuer=True)

    assert result is RescueResult.SUCCESS
    assert rescuer.get_vimcoin() == 50
    assert downed_user.get_vimcoin() == 10
    assert downed_user.get_health() == REVIVE_HEALTH
    assert await downed_user.is_down() is False

    row = await _load(factory, "rescuer")
    assert row.vimcoin == 50
    row = await _load(factory, "downed")
    assert row.health == REVIVE_HEALTH
    assert row.downed_at is None


@pytest.mark.asyncio
async def test_rescue_success_paid_by_downed(user_db):
    """由被救者支付费用：扣除被救者 50 vi"""
    from nonebot_plugin_larkuser.utils.downed import RescueResult, process_rescue

    factory, add_user = user_db
    await add_user("rescuer", vimcoin=10)
    await add_user("downed", vimcoin=80, health=0, downed_at=datetime.now() - timedelta(minutes=10))

    rescuer = await _make_user("rescuer")
    downed_user = await _make_user("downed")
    result = await process_rescue(rescuer, downed_user, pay_by_rescuer=False)

    assert result is RescueResult.SUCCESS
    assert downed_user.get_vimcoin() == 30
    assert downed_user.get_health() == 5
    assert rescuer.get_vimcoin() == 10


@pytest.mark.asyncio
async def test_rescue_target_not_downed(user_db):
    """目标没有倒地时不执行任何扣费"""
    from nonebot_plugin_larkuser.utils.downed import RescueResult, process_rescue

    factory, add_user = user_db
    await add_user("rescuer", vimcoin=100)
    await add_user("healthy", vimcoin=0)

    rescuer = await _make_user("rescuer")
    healthy = await _make_user("healthy")
    result = await process_rescue(rescuer, healthy, pay_by_rescuer=True)

    assert result is RescueResult.NOT_DOWNED
    assert rescuer.get_vimcoin() == 100


@pytest.mark.asyncio
async def test_rescue_rescuer_insufficient_vimcoin(user_db):
    """救人者余额不足时不扣费、不救起"""
    from nonebot_plugin_larkuser.utils.downed import RescueResult, process_rescue

    factory, add_user = user_db
    await add_user("rescuer", vimcoin=49)
    await add_user("downed", health=0, downed_at=datetime.now() - timedelta(minutes=10))

    rescuer = await _make_user("rescuer")
    downed_user = await _make_user("downed")
    result = await process_rescue(rescuer, downed_user, pay_by_rescuer=True)

    assert result is RescueResult.INSUFFICIENT_VIMCOIN
    assert downed_user.get_health() == 0
    assert downed_user.downed_at is not None


@pytest.mark.asyncio
async def test_rescue_downed_insufficient_vimcoin(user_db):
    """选择由被救者支付但余额不足时不扣费、不救起"""
    from nonebot_plugin_larkuser.utils.downed import RescueResult, process_rescue

    factory, add_user = user_db
    await add_user("rescuer", vimcoin=100)
    await add_user("downed", vimcoin=20, health=0, downed_at=datetime.now() - timedelta(minutes=10))

    rescuer = await _make_user("rescuer")
    downed_user = await _make_user("downed")
    result = await process_rescue(rescuer, downed_user, pay_by_rescuer=False)

    assert result is RescueResult.TARGET_INSUFFICIENT_VIMCOIN
    assert downed_user.get_vimcoin() == 20
    assert downed_user.get_health() == 0
    assert downed_user.downed_at is not None


@pytest.mark.asyncio
async def test_rescue_cost_is_fifty():
    """救起费用应为 50 vi"""
    from nonebot_plugin_larkuser.utils.downed import RESCUE_COST

    assert RESCUE_COST == 50


@pytest.mark.asyncio
async def test_rescue_expired_down_reports_not_downed(user_db):
    """目标倒地已超过 3 小时时，is_down 会先自动恢复（1 HP），救起返回未倒地"""
    from nonebot_plugin_larkuser.utils.downed import RescueResult, process_rescue

    factory, add_user = user_db
    await add_user("rescuer", vimcoin=100)
    await add_user("downed", health=0, downed_at=datetime.now() - timedelta(hours=4))

    rescuer = await _make_user("rescuer")
    downed_user = await _make_user("downed")
    result = await process_rescue(rescuer, downed_user, pay_by_rescuer=True)

    assert result is RescueResult.NOT_DOWNED
    assert downed_user.get_health() == 1
    assert rescuer.get_vimcoin() == 100


# ------------------------------------------------------------ 指令交互流程 --


@pytest.mark.asyncio
async def test_rescue_matcher_registered():
    """rescue 指令应已注册"""
    from nonebot.matcher import Matcher
    from nonebot_plugin_larkuser.matchers import rescue

    assert isinstance(rescue.rescue, type) and issubclass(rescue.rescue, Matcher)
    assert rescue.rescue.handlers
