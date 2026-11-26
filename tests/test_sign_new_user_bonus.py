"""新用户签到福利的回归测试。

需求：新注册用户（包括自动注册的用户）前 3 次使用签到，每次额外获得 100 VimCoin。
"前 3 次"按累计使用签到的次数算（不受断签影响），此前已经注册但从未签到的用户
同样视为新用户；第 4 次起不再发放。
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class _FakeLang:
    async def text(self, key: str, _user_id: str, *args: object) -> str:
        return f"{key}:{args}"


class _FakeUser:
    """只实现签到奖励用到的用户接口"""

    def __init__(self, level: int = 10, fav: float = 1.0, vimcoin: float = 1000.0) -> None:
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


async def _seed_sign_data(
    factory,
    user_id: str,
    total_sign_count: int,
    sign_days: int = 3,
    days_ago: int = 1,
) -> None:
    from nonebot_plugin_sign.models import SignData

    async with factory() as session:
        session.add(
            SignData(
                user_id=user_id,
                sign_days=sign_days,
                last_sign=date.today() - timedelta(days=days_ago),
                total_sign_count=total_sign_count,
            ),
        )
        await session.commit()


async def _get_total_sign_count(factory, user_id: str) -> int:
    from nonebot_plugin_sign.models import SignData

    async with factory() as session:
        data = await session.get_one(SignData, {"user_id": user_id})
        return data.total_sign_count


@pytest.mark.parametrize("signed_before", [0, 1, 2])
@pytest.mark.asyncio
async def test_first_three_signs_get_new_user_bonus(sign_module, signed_before: int) -> None:
    """前 3 次使用签到都给 100vi 额外奖励，且计入 vim.add"""
    module, user, factory = sign_module
    user_id = f"u-new-{signed_before}"
    await _seed_sign_data(factory, user_id, total_sign_count=signed_before)

    balance_before = user.vimcoin
    result = await module.perform_sign(user_id)

    assert result is not None
    assert result["vim"]["bonus"] == pytest.approx(module.SIGN_NEW_USER_BONUS_VIM)
    assert result["vim"]["add"] == pytest.approx(result["vim"]["formula"] + module.SIGN_NEW_USER_BONUS_VIM)
    # 实际入账 = 公式奖励 + 新人福利
    assert user.vimcoin == pytest.approx(balance_before + result["vim"]["add"])
    assert result["total_sign_count"] == signed_before + 1


@pytest.mark.asyncio
async def test_no_bonus_from_fourth_sign(sign_module) -> None:
    """第 4 次使用签到起不再发放新人福利"""
    module, user, factory = sign_module
    await _seed_sign_data(factory, "u-old", total_sign_count=3)

    balance_before = user.vimcoin
    result = await module.perform_sign("u-old")

    assert result is not None
    assert result["vim"]["bonus"] == 0
    assert result["vim"]["add"] == pytest.approx(result["vim"]["formula"])
    assert user.vimcoin == pytest.approx(balance_before + result["vim"]["add"])
    assert result["total_sign_count"] == 4


@pytest.mark.asyncio
async def test_registered_without_sign_history_is_new_user(sign_module) -> None:
    """此前已注册、但 SignData 里还没有签到记录（累计次数 0）的用户也算新用户"""
    from nonebot_plugin_sign.models import SignData

    module, _user, factory = sign_module
    # 模拟 "查过一次签到状态" 顺带建出的空记录：从未签到、累计次数为 0
    async with factory() as session:
        session.add(SignData(user_id="u-registered"))
        await session.commit()

    result = await module.perform_sign("u-registered")

    assert result is not None
    assert result["vim"]["bonus"] == pytest.approx(module.SIGN_NEW_USER_BONUS_VIM)
    assert result["total_sign_count"] == 1


@pytest.mark.asyncio
async def test_bonus_not_halved_by_bad_luck(sign_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """霉运 buff 只影响公式奖励，新人福利固定发放 100vi"""
    module, user, factory = sign_module
    monkeypatch.setattr(module, "get_bad_luck_multiplier", AsyncMock(return_value=0.5))
    await _seed_sign_data(factory, "u-unlucky", total_sign_count=0, sign_days=0)
    # 连续签到 1 天时的公式奖励（fixture 把随机数固定成 1.0），霉运按 0.5 折算
    formula = module._sign_vim_formula(user.level, user.fav, 1, 1.0, 1.0)  # ruff: ignore[private-member-access]

    result = await module.perform_sign("u-unlucky")

    assert result is not None
    assert result["vim"]["formula"] == pytest.approx(round(formula * 0.5, 1))
    assert result["vim"]["bonus"] == pytest.approx(module.SIGN_NEW_USER_BONUS_VIM)
    assert result["vim"]["add"] == pytest.approx(result["vim"]["formula"] + module.SIGN_NEW_USER_BONUS_VIM)


@pytest.mark.asyncio
async def test_already_signed_today_does_not_consume_bonus(sign_module) -> None:
    """当天重复签到直接返回 None，不消耗前 3 次的新人福利"""
    from nonebot_plugin_sign.models import SignData

    module, _user, factory = sign_module
    async with factory() as session:
        session.add(SignData(user_id="u-today", sign_days=1, last_sign=date.today(), total_sign_count=1))
        await session.commit()

    assert await module.perform_sign("u-today") is None
    assert await _get_total_sign_count(factory, "u-today") == 1


@pytest.mark.asyncio
async def test_resign_bonus_awarded_once(sign_module, monkeypatch: pytest.MonkeyPatch) -> None:
    """补签（一次 /sign 调用）只发一次新人福利，补签的历史天数不再重复发放"""
    module, user, factory = sign_module
    # 好感度在补签循环前会 +0.001，打桩掉它，好让公式期望值可以精确计算
    monkeypatch.setattr(
        module,
        "_calc_sign_fav",
        AsyncMock(return_value={"text": "", "add": 1, "now": 1, "origin": 0}),
    )
    await _seed_sign_data(factory, "u-resign", total_sign_count=0, sign_days=1, days_ago=3)

    balance_before = user.vimcoin
    level, fav = user.level, user.fav
    result = await module.perform_sign("u-resign", missed_days=2)

    assert result is not None
    assert result["resign"] is not None
    assert result["vim"]["bonus"] == pytest.approx(module.SIGN_NEW_USER_BONUS_VIM)
    assert result["total_sign_count"] == 1
    # 补签收益只含公式奖励，不含新人福利（公式里的随机数在 fixture 里固定为 1.0）
    expected_resign_vim = round(
        sum(
            module._sign_vim_formula(level, fav, day, 1.0, 1.0) for day in (1, 2)
        ),  # ruff: ignore[private-member-access]
        1,
    )
    assert result["resign"]["vim"] == pytest.approx(expected_resign_vim)
    assert user.vimcoin == pytest.approx(
        balance_before - result["resign"]["cost"] + result["vim"]["add"] + result["resign"]["vim"],
    )
