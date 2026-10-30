"""人品值读写的并发安全回归测试。

覆盖：首次生成并落库、当日记录复用、跨天记录刷新、人品值修正钩子，
以及 MySQL / MariaDB 返回 1020（Record has changed since last read）时的重试。

并发冲突在 SQLite 上无法稳定复现，因此这里直接让第一次 commit 抛出与生产环境
相同的 OperationalError，验证 get_luck_value 会重开事务重试并最终成功。
"""

from collections.abc import AsyncGenerator, Callable
from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

LuckSessionFactory = Callable[[], AsyncSession]


@pytest.fixture
async def luck_db(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[LuckSessionFactory, None]:
    """建立 LuckValue 的内存数据库，并把 jrrp 模块的 get_session 指向它"""
    import nonebot_plugin_larkutils.jrrp as jrrp

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(jrrp.LuckValue.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(jrrp, "get_session", lambda **_: factory())
    # 不加载 buff 插件注册的钩子，避免测试额外依赖 buff 数据表
    monkeypatch.setattr(jrrp, "_luck_value_hooks", [])

    yield factory
    await engine.dispose()


def _mysql_operational_error(code: int, message: str) -> OperationalError:
    return OperationalError("UPDATE nonebot_plugin_larkutils_luckvalue SET luck_value=1", {}, Exception(code, message))


@pytest.mark.asyncio
async def test_get_luck_value_generates_then_reuses(luck_db: LuckSessionFactory) -> None:
    """首次读取生成并持久化今日人品值，之后的读取复用同一个值"""
    import nonebot_plugin_larkutils.jrrp as jrrp

    value = await jrrp.get_luck_value("reuse-user")
    assert 0 <= value <= 100
    assert await jrrp.get_luck_value("reuse-user") == value

    async with luck_db() as session:
        record = await session.get(jrrp.LuckValue, {"user_id": "reuse-user"})
        assert record is not None
        assert record.luck_value == value
        assert record.generate_date == date.today()
        assert record.reroll_count == 0


@pytest.mark.asyncio
async def test_get_luck_value_refreshes_stale_record(luck_db: LuckSessionFactory) -> None:
    """跨天的旧记录会被重置为今日人品值"""
    import nonebot_plugin_larkutils.jrrp as jrrp

    yesterday = date.today() - timedelta(days=1)
    async with luck_db() as session:
        session.add(jrrp.LuckValue(user_id="stale-user", luck_value=7, generate_date=yesterday, reroll_count=4))
        await session.commit()

    value, reroll_count = await jrrp.get_luck_value_with_reroll_count("stale-user")
    assert 0 <= value <= 100
    assert reroll_count == 0

    async with luck_db() as session:
        record = await session.get(jrrp.LuckValue, {"user_id": "stale-user"})
        assert record is not None
        assert record.generate_date == date.today()
        assert record.luck_value == value
        assert record.reroll_count == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("luck_db")
async def test_get_luck_value_applies_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    """生成人品值时按注册顺序应用修正钩子"""
    import nonebot_plugin_larkutils.jrrp as jrrp

    async def hook(_user_id: str, _value: int) -> int:
        return 42

    monkeypatch.setattr(jrrp, "_luck_value_hooks", [hook])
    assert await jrrp.get_luck_value("hooked-user") == 42


@pytest.mark.asyncio
async def test_get_luck_value_retries_on_checkread(
    luck_db: LuckSessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """遇到 1020 时重开事务重试，而不是把异常抛给指令处理器"""
    import nonebot_plugin_larkutils.jrrp as jrrp

    original_commit = AsyncSession.commit
    attempts = 0

    async def flaky_commit(self: AsyncSession) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _mysql_operational_error(
                1020,
                "Record has changed since last read in table 'nonebot_plugin_larkutils_luckvalue'",
            )
        await original_commit(self)

    monkeypatch.setattr(AsyncSession, "commit", flaky_commit)

    value = await jrrp.get_luck_value("retry-user")
    assert 0 <= value <= 100
    assert attempts == 2

    async with luck_db() as session:
        record = await session.get(jrrp.LuckValue, {"user_id": "retry-user"})
        assert record is not None
        assert record.luck_value == value


@pytest.mark.asyncio
async def test_reroll_luck_value_respects_limit(luck_db: LuckSessionFactory) -> None:
    """重算会更新已重算次数，达到上限后返回 None"""
    import nonebot_plugin_larkutils.jrrp as jrrp

    async with luck_db() as session:
        session.add(jrrp.LuckValue(user_id="reroll-user", luck_value=50, generate_date=date.today(), reroll_count=0))
        await session.commit()

    result = await jrrp.reroll_luck_value("reroll-user", max_reroll_count=1)
    assert result is not None
    value, reroll_count = result
    assert 0 <= value <= 100
    assert reroll_count == 1

    assert await jrrp.reroll_luck_value("reroll-user", max_reroll_count=1) is None


@pytest.mark.asyncio
async def test_save_luck_trend_upserts(monkeypatch: pytest.MonkeyPatch) -> None:
    """同一用户同一天重复写入走势时更新原记录，而不是与并发写入冲突"""
    import nonebot_plugin_jrrp.utils as utils

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(utils.LuckTrend.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(utils, "get_session", lambda **_: factory())

    today = utils._today()
    await utils.save_luck_trend("trend-user", 33, 0)
    await utils.save_luck_trend("trend-user", 66, 1)

    async with factory() as session:
        record = await session.get(utils.LuckTrend, {"user_id": "trend-user", "record_date": today})
        assert record is not None
        assert record.luck_value == 66
        assert record.reroll_count == 1

    await engine.dispose()


def test_is_retryable_db_conflict() -> None:
    """只有瞬时并发冲突才值得重试，其它数据库错误照常抛出"""
    from nonebot_plugin_larkutils.sql import is_retryable_db_conflict

    assert is_retryable_db_conflict(_mysql_operational_error(1020, "Record has changed since last read in table"))
    assert is_retryable_db_conflict(_mysql_operational_error(1205, "Lock wait timeout exceeded"))
    assert is_retryable_db_conflict(_mysql_operational_error(1213, "Deadlock found when trying to get lock"))
    assert is_retryable_db_conflict(
        IntegrityError("INSERT ...", {}, Exception(1062, "Duplicate entry 'u1' for key 'PRIMARY'")),
    )
    assert not is_retryable_db_conflict(_mysql_operational_error(1048, "Column 'x' cannot be null"))
    assert not is_retryable_db_conflict(ValueError("boom"))
