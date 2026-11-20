"""补签花费（VimCoin 回收率）的回归测试。

需求：补签后按预期只能收回 50%（补 1 天）~10%（补 15 天）的 VimCoin，
即补签费用 = 补签奖励的期望值 / 回收率，补的天数越多越亏。
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class _FakeLang:
    async def text(self, key: str, _user_id: str, *args: object) -> str:
        return f"{key}:{args}"


class _FakeUser:
    """只实现补签花费与签到奖励用到的用户接口"""

    def __init__(self, level: int = 10, fav: float = 1.0, vimcoin: float = 100000.0) -> None:
        self.level = level
        self.fav = fav
        self.vimcoin = vimcoin
        self.experience = 0

    def get_level(self) -> int:
        return self.level

    def get_fav(self) -> float:
        return self.fav

    def get_vimcoin(self) -> float:
        return self.vimcoin

    def get_experience(self) -> int:
        return self.experience

    def get_display_fav(self) -> int:
        return round(self.fav * 1000)

    async def add_vimcoin(self, count: float) -> None:
        self.vimcoin += count

    async def use_vimcoin(self, count: float) -> bool:
        if self.vimcoin < count:
            return False
        self.vimcoin -= count
        return True

    async def add_experience(self, count: int) -> None:
        self.experience += count

    async def add_fav(self, count: float) -> None:
        self.fav += count


def test_resign_recovery_rate_endpoints() -> None:
    """回收率端点：补 1 天 50%、补 15 天 10%，中间单调递减且不低于 10%"""
    from nonebot_plugin_sign.__main__ import get_resign_recovery_rate

    assert get_resign_recovery_rate(1) == pytest.approx(0.5)
    assert get_resign_recovery_rate(15) == pytest.approx(0.1)
    rates = [get_resign_recovery_rate(days) for days in range(1, 16)]
    assert rates == sorted(rates, reverse=True)
    # 超过 15 天不再继续降低回收率
    assert get_resign_recovery_rate(30) == pytest.approx(0.1)


@pytest.mark.parametrize("missed_days", list(range(1, 15)))
def test_resign_cost_keeps_expected_recovery_rate(missed_days: int) -> None:
    """补签费用按期望收益 / 回收率折算：收益 / 费用 ≈ 目标回收率"""
    from nonebot_plugin_sign.__main__ import _expected_sign_vim, get_resign_cost, get_resign_recovery_rate

    user = _FakeUser()
    cost = get_resign_cost(user, missed_days)
    expected_vim = sum(_expected_sign_vim(user.level, user.fav, day) for day in range(1, missed_days + 1))

    assert cost > 0
    assert expected_vim / cost == pytest.approx(get_resign_recovery_rate(missed_days), rel=0.01)


def test_resign_cost_increases_with_missed_days() -> None:
    """补的天数越多总费用越高"""
    from nonebot_plugin_sign.__main__ import get_resign_cost

    user = _FakeUser()
    costs = [get_resign_cost(user, days) for days in range(1, 15)]
    assert costs == sorted(costs)
    assert len(set(costs)) == len(costs)


@pytest.fixture
async def sign_db():
    """只建立 SignData 表的内存数据库，返回会话工厂"""
    from nonebot_plugin_sign.models import SignData

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SignData.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def sign_module(monkeypatch: pytest.MonkeyPatch, sign_db):
    """打桩签到模块的数据库会话、用户查询、随机数、霉运 buff 与文案"""
    import nonebot_plugin_sign.__main__ as module

    user = _FakeUser()
    monkeypatch.setattr(module, "get_session", lambda **_: sign_db())
    monkeypatch.setattr(module, "get_user", AsyncMock(return_value=user))
    monkeypatch.setattr(module, "get_bad_luck_multiplier", AsyncMock(return_value=1.0))
    monkeypatch.setattr(module, "lang", _FakeLang())
    monkeypatch.setattr(module.random, "random", lambda: 1.0)
    return module, user, sign_db


async def _seed_sign_data(factory, user_id: str, days_since: int, sign_days: int = 2) -> None:
    from nonebot_plugin_sign.models import SignData

    async with factory() as session:
        session.add(SignData(user_id=user_id, sign_days=sign_days, last_sign=date.today() - timedelta(days=days_since)))
        await session.commit()


@pytest.mark.asyncio
async def test_perform_sign_deducts_resign_cost(sign_module) -> None:
    """补签成功时按 get_resign_cost 扣除 VimCoin，补签收益记入结果"""
    module, user, factory = sign_module
    await _seed_sign_data(factory, "u-resign", days_since=4)

    expected_cost = module.get_resign_cost(user, 3)
    balance_before = user.vimcoin
    result = await module.perform_sign("u-resign", missed_days=3)

    assert result is not None
    resign = result["resign"]
    assert resign is not None
    assert resign["cost"] == expected_cost
    assert resign["vim"] > 0
    # 余额 = 原有 - 补签费用 + 当天签到收益 + 补签收益
    assert user.vimcoin == pytest.approx(balance_before - expected_cost + result["vim"]["add"] + resign["vim"])


@pytest.mark.asyncio
async def test_perform_sign_uses_quoted_resign_cost(sign_module) -> None:
    """补签询问时报出的价格就是实际扣除的金额"""
    module, user, factory = sign_module
    await _seed_sign_data(factory, "u-quoted", days_since=4)

    balance_before = user.vimcoin
    result = await module.perform_sign("u-quoted", missed_days=3, resign_cost=777)

    assert result is not None
    assert result["resign"] is not None
    assert result["resign"]["cost"] == 777
    assert user.vimcoin == pytest.approx(balance_before - 777 + result["vim"]["add"] + result["resign"]["vim"])


@pytest.mark.asyncio
async def test_perform_sign_skips_resign_when_vimcoin_short(sign_module) -> None:
    """余额不足时不扣费、不补签，按断签处理（连续签到重置）"""
    module, user, factory = sign_module
    await _seed_sign_data(factory, "u-poor", days_since=4)

    cost = module.get_resign_cost(user, 3)
    user.vimcoin = cost - 1
    result = await module.perform_sign("u-poor", missed_days=3)

    assert result is not None
    assert result["resign"] is None
    assert result["sign_days"] == 1
    assert user.vimcoin == pytest.approx(cost - 1 + result["vim"]["add"])


@pytest.mark.asyncio
async def test_perform_sign_does_not_charge_for_normal_sign(sign_module) -> None:
    """连续签到时不会扣补签费用"""
    module, user, factory = sign_module
    await _seed_sign_data(factory, "u-normal", days_since=1, sign_days=5)

    balance_before = user.vimcoin
    result = await module.perform_sign("u-normal")

    assert result is not None
    assert result["resign"] is None
    assert result["sign_days"] == 6
    assert user.vimcoin == pytest.approx(balance_before + result["vim"]["add"])
