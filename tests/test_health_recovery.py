"""HP 恢复定时任务（nonebot_plugin_health_recovery）的回归测试。

覆盖以下场景：

- 最近一小时活跃的用户每小时回复 5 HP，不活跃用户不变；
- 倒地超过 3 小时的用户 HP 重置为 1，未超时的倒地用户不变；
- 定时任务与其它写操作（扣血）并发时不会丢失更新——两者都通过用户写锁基于数据库
  最新值修改，最终结果与串行执行一致。
"""

import asyncio
import importlib
from datetime import datetime, timedelta
from typing import Optional

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def recovery_db(tmp_path, monkeypatch):
    """建立 UserData / LastSeenRecord / MainAccountMapping 的临时数据库，并替换 get_session

    使用文件数据库而不是 ``sqlite+aiosqlite://`` 内存库：内存库在 aiosqlite 下共用同一个
    DBAPI 连接，并发测试里两个会话同时持有事务会互相干扰（会看到「更新丢失」的假象）。
    文件库每个会话各占一个连接，行为与生产（MySQL）一致。
    """
    from nonebot_plugin_larkuser.models import UserData
    from nonebot_plugin_last_seen.models import LastSeenRecord
    from nonebot_plugin_larkutils.models import MainAccountMapping

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'recovery.db'}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(UserData.__table__.create)
        await conn.run_sync(LastSeenRecord.__table__.create)
        await conn.run_sync(MainAccountMapping.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    modules = [
        "nonebot_plugin_larkuser.user.base",
        "nonebot_plugin_larkuser.user.registered",
        "nonebot_plugin_larkuser.user.utils",
        "nonebot_plugin_larkutils.subaccount",
        "nonebot_plugin_health_recovery.__main__",
    ]
    for module_path in modules:
        monkeypatch.setattr(importlib.import_module(module_path), "get_session", lambda **_: factory())

    async def add_user(
        user_id: str,
        *,
        health: float = 100.0,
        downed_at: Optional[datetime] = None,
        last_seen: Optional[datetime] = None,
    ) -> None:
        async with factory() as session:
            session.add(
                UserData(
                    user_id=user_id,
                    nickname="",
                    register_time=datetime.now(),
                    health=health,
                    downed_at=downed_at,
                    config="{}",
                )
            )
            if last_seen is not None:
                session.add(LastSeenRecord(user_id=user_id, session_id="global", last_seen=last_seen))
            await session.commit()

    async def load(user_id: str):
        async with factory() as session:
            return await session.get(UserData, {"user_id": user_id})

    yield factory, add_user, load
    await engine.dispose()


async def _run_recovery() -> None:
    from nonebot_plugin_health_recovery.__main__ import recover_health

    await recover_health()


@pytest.mark.asyncio
async def test_recovery_heals_only_active_users(recovery_db):
    """最近一小时活跃的用户 +5 HP（封顶 100），不活跃 / 满血用户不变"""
    _, add_user, load = recovery_db
    now = datetime.now()
    await add_user("20001", health=50.0, last_seen=now - timedelta(minutes=10))
    await add_user("20002", health=50.0, last_seen=now - timedelta(hours=2))
    await add_user("20003", health=100.0, last_seen=now - timedelta(minutes=10))
    await add_user("20004", health=98.0, last_seen=now - timedelta(minutes=10))

    await _run_recovery()

    assert (await load("20001")).health == pytest.approx(55.0)
    assert (await load("20002")).health == pytest.approx(50.0)
    assert (await load("20003")).health == pytest.approx(100.0)
    # 回复量不会把 HP 顶过上限
    assert (await load("20004")).health == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_recovery_revives_only_expired_downed_users(recovery_db):
    """倒地超过 3 小时的用户 HP 重置为 1，未超时的倒地用户保持原样"""
    _, add_user, load = recovery_db
    now = datetime.now()
    await add_user("20011", health=0.0, downed_at=now - timedelta(hours=4))
    await add_user("20012", health=0.0, downed_at=now - timedelta(hours=1))

    await _run_recovery()

    revived = await load("20011")
    assert revived.health == pytest.approx(1.0)
    assert revived.downed_at is None
    # 复活不是死亡，死亡计数不应该增加
    assert revived.death_count == 0

    waiting = await load("20012")
    assert waiting.health == pytest.approx(0.0)
    assert waiting.downed_at is not None


@pytest.mark.asyncio
async def test_recovery_respects_user_write_lock(recovery_db):
    """定时回复要在用户写锁内基于最新值修改，不能用扫描时的过期快照覆盖并发写入。

    测试流程：先持有用户写锁 → 启动定时任务（它会扫描到 50 血）→ 另一个「协程」把血量
    改成 20 后释放锁 → 定时任务被唤醒。
    正确实现：锁内重新读到 20，写回 25；
    旧实现（直接写 ORM 行）：会用扫描到的 50 写成 55，或直接覆盖掉 20。
    """
    factory, add_user, load = recovery_db
    await add_user("20021", health=50.0, last_seen=datetime.now())

    from nonebot_plugin_larkuser.models import UserData
    from nonebot_plugin_larkuser.user.lock import user_write_lock

    async with user_write_lock("20021"):
        task = asyncio.create_task(_run_recovery())
        # 让定时任务完成「扫描候选用户」，停在获取用户写锁处
        await asyncio.sleep(0.2)
        async with factory() as session:
            row = await session.get(UserData, {"user_id": "20021"})
            row.health = 20.0
            await session.commit()

    await asyncio.wait_for(task, timeout=30)
    assert (await load("20021")).health == pytest.approx(25.0)
