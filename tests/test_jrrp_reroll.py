"""``/jrrp reroll`` 计数与计费的并发回归测试。

背景（PR #1601 的 E2E 报告「发现 1」）：三条并发 ``/jrrp reroll`` 都回复
「1/3 次 / 60 vi」，``reroll_count`` 最终只到 1。原因是「读已重算次数 → 计费 →
扣费 → 写回次数」之间有多个 await，几个协程基于同一份第 1 次快照各自按首档计费；
SQLite 会忽略 ``SELECT ... FOR UPDATE``，所以在沙箱/单进程里同样会丢失更新，
用户可以用首档价格一直重算并绕过 ``jrrp_reroll_max_count``。

修好后整段临界区在用户级锁内串行执行：并发重算依次拿到 1/2/3 次与 60/120/180 vi。
并发测试用文件版 SQLite（内存库共用同一个 DBAPI 连接，会掩盖丢失更新）。
"""

import asyncio
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

LuckSessionFactory = Callable[[], AsyncSession]


class FakeUser:
    """只实现重算用到的余额接口，并模拟 larkuser 的相对扣费与写锁语义。"""

    def __init__(self, balance: float) -> None:
        self.balance = balance
        self._lock = asyncio.Lock()

    async def use_vimcoin(self, cost: float) -> bool:
        async with self._lock:
            # 放大并发窗口：没有串行化时几路重算会在这里交错
            await asyncio.sleep(0)
            if self.balance < cost:
                return False
            self.balance -= cost
            return True

    async def add_vimcoin(self, count: float) -> None:
        async with self._lock:
            self.balance += count

    def get_vimcoin(self) -> float:
        return self.balance


@pytest.fixture
async def reroll_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[LuckSessionFactory, None]:
    """建立 LuckValue 的临时文件库，并把 jrrp 模块的 get_session 指向它"""
    import nonebot_plugin_larkutils.jrrp as jrrp

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'luck.db'}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(jrrp.LuckValue.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(jrrp, "get_session", lambda **_: factory())
    # 不加载 buff 插件注册的钩子，避免测试依赖 buff 数据表；同时关掉 6 月偏移，
    # 让「人品值到顶」等用例与运行日期无关
    monkeypatch.setattr(jrrp, "_luck_value_hooks", [])
    monkeypatch.setattr(jrrp, "_get_june_bias", lambda _today=None: 0)

    yield factory
    await engine.dispose()


async def _seed(factory: LuckSessionFactory, user_id: str, luck_value: int, reroll_count: int) -> None:
    import nonebot_plugin_larkutils.jrrp as jrrp

    async with factory() as session:
        session.add(
            jrrp.LuckValue(
                user_id=user_id,
                luck_value=luck_value,
                generate_date=date.today(),
                reroll_count=reroll_count,
            ),
        )
        await session.commit()


async def _get_record(factory: LuckSessionFactory, user_id: str):
    import nonebot_plugin_larkutils.jrrp as jrrp

    async with factory() as session:
        return await session.get(jrrp.LuckValue, {"user_id": user_id})


@pytest.mark.asyncio
@pytest.mark.usefixtures("reroll_db")
async def test_concurrent_rerolls_use_increasing_price() -> None:
    """三个并发重算：次数依次 1/2/3，价格依次 60/120/180，余额只少 360"""
    from nonebot_plugin_jrrp.utils import perform_reroll

    user = FakeUser(1000)
    outcomes = await asyncio.gather(*(perform_reroll(user, "concurrent-user", 3, 60) for _ in range(3)))

    assert [outcome.status for outcome in outcomes] == ["ok", "ok", "ok"]
    assert sorted(outcome.reroll_count for outcome in outcomes) == [1, 2, 3]
    assert sorted(outcome.cost for outcome in outcomes) == [60, 120, 180]
    assert user.balance == 1000 - 60 - 120 - 180


@pytest.mark.asyncio
async def test_concurrent_rerolls_persist_count(reroll_db: LuckSessionFactory) -> None:
    """并发重算结束后数据库里的已重算次数应为 3，而不是被覆盖成 1"""
    from nonebot_plugin_jrrp.utils import perform_reroll

    user = FakeUser(1000)
    await asyncio.gather(*(perform_reroll(user, "persist-user", 3, 60) for _ in range(3)))

    record = await _get_record(reroll_db, "persist-user")
    assert record is not None
    assert record.reroll_count == 3


@pytest.mark.asyncio
async def test_reroll_rejected_at_limit_without_charge(reroll_db: LuckSessionFactory) -> None:
    """达到重算上限时直接拒绝，不扣费也不改数据"""
    from nonebot_plugin_jrrp.utils import perform_reroll

    await _seed(reroll_db, "limit-user", 50, 3)
    user = FakeUser(1000)

    outcome = await perform_reroll(user, "limit-user", 3, 60)

    assert outcome.status == "max_reached"
    assert user.balance == 1000
    record = await _get_record(reroll_db, "limit-user")
    assert record is not None
    assert record.reroll_count == 3
    assert record.luck_value == 50


@pytest.mark.asyncio
async def test_reroll_perfect_luck_does_not_charge(reroll_db: LuckSessionFactory) -> None:
    """人品值已到顶时不扣费就返回提示（旧实现先扣费再发现不能重算）"""
    from nonebot_plugin_jrrp.utils import perform_reroll

    await _seed(reroll_db, "perfect-user", 100, 0)
    user = FakeUser(1000)

    outcome = await perform_reroll(user, "perfect-user", 3, 60)

    assert outcome.status == "perfect_luck"
    assert user.balance == 1000
    record = await _get_record(reroll_db, "perfect-user")
    assert record is not None
    assert record.reroll_count == 0


@pytest.mark.asyncio
async def test_reroll_insufficient_vimcoin_keeps_count(reroll_db: LuckSessionFactory) -> None:
    """余额不足时不消耗重算次数，也不改人品值"""
    from nonebot_plugin_jrrp.utils import perform_reroll

    await _seed(reroll_db, "poor-user", 50, 1)
    user = FakeUser(30)

    outcome = await perform_reroll(user, "poor-user", 3, 60)

    assert outcome.status == "insufficient_vimcoin"
    assert outcome.cost == 120
    assert outcome.balance == 30
    record = await _get_record(reroll_db, "poor-user")
    assert record is not None
    assert record.reroll_count == 1
    assert record.luck_value == 50
