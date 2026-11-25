"""LarkUser 并发写入回归测试。

覆盖以下场景（对应 VimCoin 等数值在高并发下丢失更新的漏洞）：

- 同一用户并发 ``add_vimcoin`` 不会丢失更新；
- 同一用户并发 ``use_vimcoin`` 不会透支（余额判断与扣费在同一把锁内）；
- 同一用户并发 ``set_config_key`` 不会互相覆盖配置项；
- 同一用户并发 ``damage`` 不会丢失扣血；
- 只读句柄调用写方法会抛出 :class:`UserNotWritable`，且不会改动数据库。
"""

import asyncio
import importlib
import json
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def user_db(monkeypatch):
    """建立 UserData / MainAccountMapping 的内存数据库，并把相关 get_session 指向它"""
    from nonebot_plugin_larkuser.models import UserData
    from nonebot_plugin_larkutils.models import MainAccountMapping

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(UserData.__table__.create)
        await conn.run_sync(MainAccountMapping.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    for module_path in (
        "nonebot_plugin_larkuser.user.base",
        "nonebot_plugin_larkuser.user.registered",
        "nonebot_plugin_larkuser.user.utils",
        "nonebot_plugin_larkutils.subaccount",
    ):
        monkeypatch.setattr(importlib.import_module(module_path), "get_session", lambda **_: factory())

    async def add_user(
        user_id: str,
        *,
        vimcoin: float = 0.0,
        health: float = 100.0,
        config: str = "{}",
    ) -> None:
        async with factory() as session:
            session.add(
                UserData(
                    user_id=user_id,
                    nickname="",
                    register_time=datetime.now(),
                    vimcoin=vimcoin,
                    health=health,
                    config=config,
                )
            )
            await session.commit()

    async def load(user_id: str):
        async with factory() as session:
            return await session.get(UserData, {"user_id": user_id})

    yield factory, add_user, load
    await engine.dispose()


async def _get_user(user_id: str, writable: bool):
    from nonebot_plugin_larkuser import get_user

    return await get_user(user_id, writable=writable)


@pytest.mark.asyncio
async def test_concurrent_add_vimcoin_keeps_every_update(user_db):
    """并发加币不应丢失更新：50 次 +1 之后余额必须是 50"""
    _, add_user, load = user_db
    await add_user("10001")

    user = await _get_user("10001", writable=True)
    await asyncio.wait_for(asyncio.gather(*(user.add_vimcoin(1.0) for _ in range(50))), timeout=30)

    assert (await load("10001")).vimcoin == pytest.approx(50.0)
    assert user.get_vimcoin() == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_concurrent_use_vimcoin_cannot_overdraw(user_db):
    """并发扣费不能透支：余额 10 时 20 个并发请求只应有 10 个成功"""
    _, add_user, load = user_db
    await add_user("10002", vimcoin=10.0)

    user = await _get_user("10002", writable=True)
    results = await asyncio.wait_for(
        asyncio.gather(*(user.use_vimcoin(1.0) for _ in range(20))),
        timeout=30,
    )

    assert sum(results) == 10
    assert (await load("10002")).vimcoin == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_concurrent_set_config_key_merges_keys(user_db):
    """并发写不同的 config key 时不能只留下最后一个"""
    _, add_user, load = user_db
    await add_user("10003")

    user = await _get_user("10003", writable=True)
    await asyncio.wait_for(
        asyncio.gather(*(user.set_config_key(f"key{i}", i) for i in range(20))),
        timeout=30,
    )

    assert json.loads((await load("10003")).config) == {f"key{i}": i for i in range(20)}


@pytest.mark.asyncio
async def test_concurrent_damage_keeps_every_hit(user_db):
    """并发扣血不应丢失：5 次 10 点伤害后 HP 应为 50"""
    _, add_user, load = user_db
    await add_user("10004", health=100.0)

    user = await _get_user("10004", writable=True)
    await asyncio.wait_for(asyncio.gather(*(user.damage(10.0) for _ in range(5))), timeout=30)

    row = await load("10004")
    assert row.health == pytest.approx(50.0)
    assert row.downed_at is None


@pytest.mark.asyncio
async def test_readonly_handle_rejects_write(user_db):
    """只读句柄调用写方法应抛出 UserNotWritable，且不产生写入"""
    from nonebot_plugin_larkuser.exceptions import UserNotWritable

    _, add_user, load = user_db
    await add_user("10005", vimcoin=5.0)

    user = await _get_user("10005", writable=False)
    with pytest.raises(UserNotWritable):
        await user.add_vimcoin(1.0)
    assert (await load("10005")).vimcoin == pytest.approx(5.0)

    # 即便最终能运行到写语句，也不允许通过只读句柄修改
    with pytest.raises(UserNotWritable):
        await user.set_config_key("key", "value")
    assert json.loads((await load("10005")).config) == {}
