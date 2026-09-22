"""霉运 buff 对各玩法的影响回归测试。

覆盖：签到的 VimCoin / 好感度减半、商店随机事件概率降低、
掷骰子失败概率提高、抽取或重抽人品值时被压分，
以及臭鸡蛋命中后附着霉运。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class _Finished(Exception):
    """用于截断 lang.finish 的哨兵异常"""


class _FakeLang:
    async def text(self, key: str, _user_id: str, *args: object) -> str:
        return f"{key}:{args}"

    async def finish(self, key: str, _user_id: str, *args: object) -> None:
        raise _Finished(key)

    async def send(self, key: str, _user_id: str, *args: object) -> None:
        return None


class _FakeSignUser:
    def __init__(self, fav: float = 1.0, vimcoin: float = 100.0, level: int = 10) -> None:
        self.fav = fav
        self.vimcoin = vimcoin
        self.level = level

    def get_level(self) -> int:
        return self.level

    def get_fav(self) -> float:
        return self.fav

    def get_vimcoin(self) -> float:
        return self.vimcoin

    def get_display_fav(self) -> int:
        return round(self.fav * 1000)

    async def add_vimcoin(self, count: float) -> None:
        self.vimcoin += count

    async def add_fav(self, count: float) -> None:
        self.fav += count


@pytest.fixture
def sign_env(monkeypatch: pytest.MonkeyPatch):
    """打桩签到模块的用户查询、文案与随机数"""
    import nonebot_plugin_sign.__main__ as module

    multiplier = {"value": 1.0}

    async def fake_multiplier(_user_id: str) -> float:
        return multiplier["value"]

    monkeypatch.setattr(module, "lang", _FakeLang())
    monkeypatch.setattr(module, "get_user", AsyncMock(return_value=_FakeSignUser()))
    monkeypatch.setattr(module.random, "random", lambda: 1.0)
    monkeypatch.setattr(module, "get_bad_luck_multiplier", fake_multiplier)
    return module, multiplier


@pytest.mark.asyncio
async def test_sign_vim_halved_by_bad_luck(sign_env) -> None:
    module, multiplier = sign_env

    multiplier["value"] = 1.0
    normal_result = await module._calc_sign_vim("u-normal", 5)
    assert normal_result["add"] > 0

    multiplier["value"] = 0.5
    halved_result = await module._calc_sign_vim("u-bad-luck", 5)
    assert halved_result["add"] == round(normal_result["add"] * 0.5, 1)


@pytest.mark.asyncio
async def test_sign_fav_halved_by_bad_luck(sign_env) -> None:
    module, multiplier = sign_env

    multiplier["value"] = 1.0
    normal_result = await module._calc_sign_fav("u-normal")
    assert normal_result["add"] == 1

    multiplier["value"] = 0.5
    halved_result = await module._calc_sign_fav("u-bad-luck")
    # 好感度减半后展示为 0.5，而不是被取整成 0
    assert halved_result["add"] == 0.5


@pytest.mark.asyncio
async def test_sign_fav_multiplier_from_real_buff(monkeypatch: pytest.MonkeyPatch) -> None:
    """不打桩 buff 查询：附着霉运后签到好感度同样减半"""
    import nonebot_plugin_buff.builtin as builtin
    import nonebot_plugin_sign.__main__ as module

    user_id = "bad-luck-sign-real"
    monkeypatch.setattr(module, "lang", _FakeLang())
    monkeypatch.setattr(module, "get_user", AsyncMock(return_value=_FakeSignUser()))

    normal_result = await module._calc_sign_fav(user_id)
    await builtin.attach_bad_luck(user_id, layers=1)
    buffed_result = await module._calc_sign_fav(user_id)

    assert normal_result["add"] == 1
    assert buffed_result["add"] == 0.5


class _FakeStack:
    def __init__(self, item_id: str, count: int = 1) -> None:
        self.item_id = item_id
        self.count = count

    async def getName(self) -> str:
        return self.item_id


@pytest.fixture
def shop_env(monkeypatch: pytest.MonkeyPatch):
    """打桩商店购买流程，记录实际发放的物品"""
    import nonebot_plugin_shop.__main__ as module

    granted: list[str] = []
    multiplier = {"value": 1.0}

    async def fake_get_item(location, _user_id, count=1, _data=None):
        return _FakeStack(str(location), count)

    async def fake_give_item(_user_id, stack):
        granted.append(stack.item_id)

    async def fake_multiplier(_user_id: str) -> float:
        return multiplier["value"]

    class _FakeUser:
        def get_vimcoin(self) -> float:
            return 100000.0

        async def use_vimcoin(self, _count: float) -> bool:
            return True

    monkeypatch.setattr(module, "lang", _FakeLang())
    monkeypatch.setattr(module, "get_goods_name", AsyncMock(return_value="鸡蛋"))
    monkeypatch.setattr(module, "get_item", fake_get_item)
    monkeypatch.setattr(module, "give_item", fake_give_item)
    monkeypatch.setattr(module, "get_location_by_id", lambda item_id: item_id)
    monkeypatch.setattr(module, "get_user", AsyncMock(return_value=_FakeUser()))
    monkeypatch.setattr(module, "get_bad_luck_multiplier", fake_multiplier)
    # 0.004：正常状态下小于 0.005 的概率，霉运减半后（0.0025）不再命中
    monkeypatch.setattr(module.random, "random", lambda: 0.004)
    return module, granted, multiplier


async def _buy_eggs(module, granted: list[str], multiplier: dict, value: float) -> list[str]:
    granted.clear()
    multiplier["value"] = value
    with pytest.raises(_Finished):
        await module.handle_buy(index=7, count=100, user_id="u-shop")
    return list(granted)


@pytest.mark.asyncio
async def test_shop_random_event_probability_lowered(shop_env) -> None:
    module, granted, multiplier = shop_env

    assert await _buy_eggs(module, granted, multiplier, 1.0) == ["moonlark:rotten_egg"]
    assert await _buy_eggs(module, granted, multiplier, 0.5) == ["moonlark:egg"]


@pytest.fixture
def roll_env(monkeypatch: pytest.MonkeyPatch):
    import nonebot_plugin_roll.__main__ as module

    monkeypatch.setattr(module, "roll_dice_value", lambda: 20)
    monkeypatch.setattr(module, "randint", lambda a, _b: a)

    def set_random(value: float) -> None:
        monkeypatch.setattr(module, "random", lambda: value)

    return module, set_random


def test_roll_without_bad_luck_keeps_value(roll_env) -> None:
    module, set_random = roll_env
    set_random(0.0)
    assert module.get_dice_value(0) == 20


def test_roll_with_bad_luck_increases_crit_fail(roll_env) -> None:
    module, set_random = roll_env
    # 霉运 1 层：大失败概率 0.1，取 0.05 必定大失败
    set_random(0.05)
    assert module.get_dice_value(1) == 1
    # 未受霉运影响时同样的随机值不会失败
    assert module.get_dice_value(0) == 20


def test_roll_with_bad_luck_increases_fail(roll_env) -> None:
    module, set_random = roll_env
    # 落在 0.1 ~ 0.35 区间内为普通失败
    set_random(0.2)
    assert module.get_dice_value(1) == 2
    assert module.get_dice_value(0) == 20


def test_roll_bad_luck_chance_is_capped(roll_env) -> None:
    module, set_random = roll_env
    # 层数再多，额外概率也不会超过上限（大失败 0.2 / 失败 0.3），0.99 仍保持原点数
    set_random(0.99)
    assert module.get_dice_value(10) == 20
    # 0.4 落在封顶后的失败区间 [0.2, 0.5) 内
    set_random(0.4)
    assert module.get_dice_value(10) == 2


@pytest.mark.asyncio
async def test_luck_hook_registered_and_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_larkutils import jrrp

    # 用新的列表替换全局钩子列表，测试结束后由 monkeypatch 还原
    monkeypatch.setattr(jrrp, "_luck_value_hooks", [])

    async def hook(_user_id: str, value: int) -> int:
        return value + 1

    jrrp.register_luck_value_hook(hook)
    assert await jrrp.apply_luck_value_hooks("u-hook", 10) == 11


@pytest.mark.asyncio
async def test_bad_luck_lowers_luck_value(monkeypatch: pytest.MonkeyPatch) -> None:
    import nonebot_plugin_jrrp.hooks as hooks

    monkeypatch.setattr(hooks.random, "random", lambda: 1.0)

    monkeypatch.setattr(hooks, "get_bad_luck_layers", AsyncMock(return_value=0))
    assert await hooks.apply_bad_luck_to_luck("u", 80) == 80

    monkeypatch.setattr(hooks, "get_bad_luck_layers", AsyncMock(return_value=1))
    assert await hooks.apply_bad_luck_to_luck("u", 80) == 40

    monkeypatch.setattr(hooks, "get_bad_luck_layers", AsyncMock(return_value=3))
    assert await hooks.apply_bad_luck_to_luck("u", 80) == 10


@pytest.mark.asyncio
async def test_bad_luck_can_zero_luck_value(monkeypatch: pytest.MonkeyPatch) -> None:
    import nonebot_plugin_jrrp.hooks as hooks

    monkeypatch.setattr(hooks, "get_bad_luck_layers", AsyncMock(return_value=1))
    monkeypatch.setattr(hooks.random, "random", lambda: 0.0)
    assert await hooks.apply_bad_luck_to_luck("u", 100) == 0


@pytest.mark.asyncio
async def test_rotten_egg_attaches_bad_luck(monkeypatch: pytest.MonkeyPatch) -> None:
    """用臭鸡蛋砸中用户会按数量附着霉运 buff"""
    import nonebot_plugin_eggstrike.__main__ as module

    attached: list[tuple[str, int]] = []

    async def fake_attach_bad_luck(user_id: str, layers: int = 1) -> None:
        attached.append((user_id, layers))

    target_user = MagicMock()
    target_user.is_registered.return_value = True
    target_user.get_health.return_value = 10.0
    target_user.damage = AsyncMock()

    monkeypatch.setattr(module, "attach_bad_luck", fake_attach_bad_luck)
    monkeypatch.setattr(module, "get_main_account", AsyncMock(return_value="target-main"))
    monkeypatch.setattr(module, "get_user", AsyncMock(return_value=target_user))
    monkeypatch.setattr(module, "get_nickname", AsyncMock(return_value="某人"))
    monkeypatch.setattr(module, "get_egg_type_name", AsyncMock(return_value="臭鸡蛋"))
    monkeypatch.setattr(module, "get_location_by_id", lambda item_id: item_id)
    monkeypatch.setattr(module, "deduct_eggs", AsyncMock())
    monkeypatch.setattr(module, "lang", _FakeLang())

    target = MagicMock()
    target.result.target = "target-native"

    with pytest.raises(_Finished):
        await module.throw_egg(
            bot=MagicMock(),
            event=MagicMock(),
            target=target,
            count=MagicMock(available=True, result=2),
            egg_type=MagicMock(available=True, result="rotten_egg"),
            user_id="thrower",
        )

    assert attached == [("target-main", 2)]
