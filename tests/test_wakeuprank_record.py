"""早起记录写入的并发安全回归测试。

背景：``wakeuprank`` 的消息监听器在 4:00-14:00 对每条消息都尝试记一次早起。一个群
里可能同时有 OneBot 与 QQ 官方两个账号，同一条消息会被两个 Bot 各处理一次，于是两
个处理器会并发写入同一个 ``(user_id, record_date)``。原实现把「查当日记录」和「插
入」放进同一个事务：两个事务都读到「今天还没有记录」，后插入的一方在 MySQL /
MariaDB 上收到的不是重复主键，而是 1020（ER_CHECKREAD，"Record has changed since
last read in table"），异常一路抛到消息处理器并上报 Sentry。

SQLite 上无法稳定复现 MySQL 的行版本冲突，所以这里让 commit 直接抛出与生产环境一致
的 OperationalError，验证：并发冲突在记录确实已经存在时被吞掉、记录只写一次、真正
的写失败仍然抛出，以及 ``valid`` 仍然按最后活跃时间判定。
"""

from collections.abc import AsyncGenerator, Callable
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

RiseSessionFactory = Callable[[], AsyncSession]

_TODAY = date(2026, 11, 24)
_WAKE_TIME = datetime(2026, 11, 24, 8, 57, 16)


@pytest.fixture
async def rise_db(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[RiseSessionFactory, None]:
    """建立早起记录相关的内存数据库，并把插件模块的 get_session 指向它"""
    import nonebot_plugin_wakeuprank.__main__ as wakeuprank

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(wakeuprank.RiseData.__table__.create)
        await conn.run_sync(wakeuprank.LastSeenRecord.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(wakeuprank, "get_session", lambda **_: factory())

    yield factory
    await engine.dispose()


def _mysql_operational_error(code: int, message: str) -> OperationalError:
    return OperationalError(
        "INSERT INTO nonebot_plugin_wakeuprank_risedata (user_id, record_date, wake_time, valid) "
        "VALUES (%s, %s, %s, %s)",
        {},
        Exception(code, message),
    )


@pytest.mark.asyncio
async def test_record_rise_writes_once(rise_db: RiseSessionFactory) -> None:
    """同一用户当天重复写入时只保留第一条记录"""
    import nonebot_plugin_wakeuprank.__main__ as wakeuprank

    await wakeuprank.record_rise("user", _TODAY, _WAKE_TIME)
    await wakeuprank.record_rise("user", _TODAY, _WAKE_TIME + timedelta(minutes=30))

    assert await wakeuprank.has_rise_record("user", _TODAY) is True
    async with rise_db() as session:
        rows = (await session.scalars(select(wakeuprank.RiseData))).all()
    assert len(rows) == 1
    assert rows[0].wake_time == _WAKE_TIME


@pytest.mark.asyncio
async def test_record_rise_swallows_conflict_when_record_exists(
    rise_db: RiseSessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """另一个处理器抢先写入同一主键时，本事务收到 1020 也不应抛给消息处理器"""
    import nonebot_plugin_wakeuprank.__main__ as wakeuprank

    real_commit = AsyncSession.commit
    concurrent_write_done = False

    async def commit_with_concurrent_writer(self: AsyncSession) -> None:
        nonlocal concurrent_write_done
        if not concurrent_write_done:
            # 模拟并发的另一个处理器在我们提交前已经写入并提交了同一行
            concurrent_write_done = True
            async with rise_db() as concurrent_session:
                concurrent_session.add(
                    wakeuprank.RiseData(
                        user_id="user",
                        record_date=_TODAY,
                        wake_time=_WAKE_TIME - timedelta(minutes=1),
                        valid=True,
                    ),
                )
                await real_commit(concurrent_session)
            raise _mysql_operational_error(
                1020,
                "Record has changed since last read in table 'nonebot_plugin_wakeuprank_risedata'",
            )
        await real_commit(self)

    monkeypatch.setattr(AsyncSession, "commit", commit_with_concurrent_writer)

    await wakeuprank.record_rise("user", _TODAY, _WAKE_TIME)

    async with rise_db() as session:
        rows = (await session.scalars(select(wakeuprank.RiseData))).all()
    assert len(rows) == 1
    assert rows[0].wake_time == _WAKE_TIME - timedelta(minutes=1)


@pytest.mark.asyncio
async def test_record_rise_reraises_conflict_without_record(
    rise_db: RiseSessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """记录并不存在时，1020 是真正的写失败，必须抛出而不是静默丢弃"""

    async def always_checkread(self: AsyncSession) -> None:
        raise _mysql_operational_error(
            1020,
            "Record has changed since last read in table 'nonebot_plugin_wakeuprank_risedata'",
        )

    monkeypatch.setattr(AsyncSession, "commit", always_checkread)

    import nonebot_plugin_wakeuprank.__main__ as wakeuprank

    with pytest.raises(OperationalError):
        await wakeuprank.record_rise("user", _TODAY, _WAKE_TIME)


@pytest.mark.asyncio
async def test_record_rise_does_not_swallow_other_errors(
    rise_db: RiseSessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """与并发无关的数据库错误应原样抛出，不能被当成重复写入吞掉"""

    async def broken_commit(self: AsyncSession) -> None:
        raise _mysql_operational_error(2013, "Lost connection to MySQL server during query")

    monkeypatch.setattr(AsyncSession, "commit", broken_commit)

    import nonebot_plugin_wakeuprank.__main__ as wakeuprank

    with pytest.raises(OperationalError):
        await wakeuprank.record_rise("user", _TODAY, _WAKE_TIME)


@pytest.mark.asyncio
async def test_valid_flag_follows_last_seen(rise_db: RiseSessionFactory) -> None:
    """一小时内活跃过的用户记一次无效记录，其余用户记为有效"""
    import nonebot_plugin_wakeuprank.__main__ as wakeuprank
    from nonebot_plugin_wakeuprank.constants import GLOBAL_SESSION_ID

    async with rise_db() as session:
        session.add(
            wakeuprank.LastSeenRecord(
                user_id="awake",
                session_id=GLOBAL_SESSION_ID,
                last_seen=_WAKE_TIME - timedelta(minutes=10),
            ),
        )
        session.add(
            wakeuprank.LastSeenRecord(
                user_id="asleep",
                session_id=GLOBAL_SESSION_ID,
                last_seen=_WAKE_TIME - timedelta(hours=2),
            ),
        )
        await session.commit()

    await wakeuprank.record_rise("awake", _TODAY, _WAKE_TIME)
    await wakeuprank.record_rise("asleep", _TODAY, _WAKE_TIME)
    await wakeuprank.record_rise("newcomer", _TODAY, _WAKE_TIME)

    async with rise_db() as session:
        rows = (await session.scalars(select(wakeuprank.RiseData))).all()
    assert {row.user_id: row.valid for row in rows} == {
        "awake": False,
        "asleep": True,
        "newcomer": True,
    }
