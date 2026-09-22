"""物品不足时的购买提示回归测试。

``/splat``、``/roll`` 在持有物品不足时会询问是否从商店购买缺口数量：
QQ 官方机器人使用 markdown + 是/否键盘按钮，其余平台保持文本 [y/n] 提示；
用户确认购买后重新尝试执行原指令。商品不在商店出售（如臭鸡蛋）时保持原提示。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class _FakeUser:
    """只实现购买所需 VimCoin 接口的用户替身"""

    def __init__(self, vimcoin: float = 0) -> None:
        self.vimcoin = vimcoin

    async def has_vimcoin(self, count: float) -> bool:
        return self.vimcoin >= count

    async def use_vimcoin(self, count: float, force: bool = False) -> bool:
        if force or await self.has_vimcoin(count):
            self.vimcoin -= count
            return True
        return False


@pytest.fixture(autouse=True)
def patched_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    """替换 LangHelper.text，避免依赖数据库中的语言文本

    注意：插件导入必须在函数/fixture 内部进行（collection 阶段 nonebot 尚未初始化）。
    """
    from nonebot_plugin_larklang.__main__ import LangHelper

    async def fake_text(_self: LangHelper, key: str, _user_id: str, *_args: object, **_kwargs: object) -> str:
        return f"text::{key}"

    monkeypatch.setattr(LangHelper, "text", fake_text)


@pytest.mark.asyncio
async def test_build_purchase_prompt_qq_uses_keyboard_buttons(monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方机器人的购买提示应为 markdown 消息，并附带 y/n 键盘按钮"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_alconna import Keyboard, Text, UniMessage

    from nonebot_plugin_shop import utils

    monkeypatch.setattr(utils, "get_goods_name", AsyncMock(return_value="二十面骰子"))
    message = await utils.build_purchase_prompt("moonlark:dice", 3, "10", MagicMock(spec=QQBot))

    assert isinstance(message, UniMessage)
    text = next(seg for seg in message if isinstance(seg, Text))
    assert text.text == "text::purchase.prompt_markdown"
    assert any("markdown" in styles for styles in text.styles.values())
    keyboard = next(seg for seg in message if isinstance(seg, Keyboard))
    buttons = list(keyboard.children)
    assert [button.text for button in buttons] == ["y", "n"]
    assert [str(button.label) for button in buttons] == ["text::purchase.button_yes", "text::purchase.button_no"]


@pytest.mark.asyncio
async def test_build_purchase_prompt_plain_text_on_other_adapters(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 QQ 平台保持文本 [y/n] 提示"""
    from nonebot_plugin_shop import utils

    monkeypatch.setattr(utils, "get_goods_name", AsyncMock(return_value="鸡蛋"))
    message = await utils.build_purchase_prompt("moonlark:egg", 2, "10", MagicMock())

    assert message == "text::purchase.prompt"


@pytest.mark.asyncio
async def test_build_purchase_prompt_rejects_item_not_in_shop() -> None:
    """商店不出售的物品无法构建购买提示"""
    from nonebot_plugin_shop import utils

    with pytest.raises(ValueError, match="not sold in shop"):
        await utils.build_purchase_prompt("moonlark:rotten_egg", 1, "10", MagicMock())


@pytest.mark.asyncio
async def test_offer_purchase_skips_item_not_in_shop(monkeypatch: pytest.MonkeyPatch) -> None:
    """选择臭鸡蛋等商店不出售的物品时不询问购买，由调用方给出原有提示"""
    from nonebot_plugin_shop import utils

    prompt_purchase = AsyncMock(return_value=True)
    monkeypatch.setattr(utils, "prompt_purchase", prompt_purchase)

    assert await utils.offer_purchase_when_short("10", "moonlark:rotten_egg", 3, MagicMock()) is False
    prompt_purchase.assert_not_awaited()


@pytest.mark.asyncio
async def test_offer_purchase_skips_prompt_when_enough(monkeypatch: pytest.MonkeyPatch) -> None:
    """持有数量足够时既不询问也不购买"""
    from nonebot_plugin_shop import utils

    prompt_purchase = AsyncMock(return_value=False)
    monkeypatch.setattr(utils, "get_goods_count", AsyncMock(return_value=5))
    monkeypatch.setattr(utils, "prompt_purchase", prompt_purchase)

    assert await utils.offer_purchase_when_short("10", "moonlark:dice", 5, MagicMock()) is True
    prompt_purchase.assert_not_awaited()


@pytest.mark.asyncio
async def test_offer_purchase_buys_shortage_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """只购买缺口数量，并在购买后重新核对持有量"""
    from nonebot_plugin_shop import utils

    counts = iter([1, 4])
    prompt_purchase = AsyncMock(return_value=True)
    monkeypatch.setattr(utils, "get_goods_count", AsyncMock(side_effect=lambda *_args: next(counts)))
    monkeypatch.setattr(utils, "prompt_purchase", prompt_purchase)

    assert await utils.offer_purchase_when_short("10", "moonlark:dice", 4, MagicMock()) is True
    prompt_purchase.assert_awaited_once()
    assert prompt_purchase.await_args.args[:3] == ("10", "moonlark:dice", 3)


@pytest.mark.asyncio
async def test_offer_purchase_returns_false_when_still_short(monkeypatch: pytest.MonkeyPatch) -> None:
    """购买后仍然不足（例如鸡蛋被替换成臭鸡蛋）时返回 False"""
    from nonebot_plugin_shop import utils

    monkeypatch.setattr(utils, "get_goods_count", AsyncMock(side_effect=[0, 0]))
    monkeypatch.setattr(utils, "prompt_purchase", AsyncMock(return_value=True))

    assert await utils.offer_purchase_when_short("10", "moonlark:egg", 2, MagicMock()) is False


@pytest.mark.asyncio
async def test_prompt_purchase_buys_after_agreement(monkeypatch: pytest.MonkeyPatch) -> None:
    """用户确认后按商店规则购买"""
    from nonebot_plugin_shop import utils

    buy_goods = AsyncMock(return_value={"moonlark:dice": 2})
    monkeypatch.setattr(utils, "get_user", AsyncMock(return_value=_FakeUser(1000)))
    monkeypatch.setattr(utils, "get_goods_name", AsyncMock(return_value="二十面骰子"))
    monkeypatch.setattr(utils, "prompt", AsyncMock(return_value=True))
    monkeypatch.setattr(utils, "buy_goods", buy_goods)

    bot = MagicMock()
    assert await utils.prompt_purchase("10", "moonlark:dice", 2, bot) is True
    buy_goods.assert_awaited_once_with("10", "moonlark:dice", 2)


@pytest.mark.asyncio
async def test_prompt_purchase_does_not_buy_when_declined(monkeypatch: pytest.MonkeyPatch) -> None:
    """用户取消购买时不扣费"""
    from nonebot_plugin_shop import utils

    buy_goods = AsyncMock()
    monkeypatch.setattr(utils, "get_user", AsyncMock(return_value=_FakeUser(1000)))
    monkeypatch.setattr(utils, "get_goods_name", AsyncMock(return_value="二十面骰子"))
    monkeypatch.setattr(utils, "prompt", AsyncMock(return_value=False))
    monkeypatch.setattr(utils, "buy_goods", buy_goods)

    assert await utils.prompt_purchase("10", "moonlark:dice", 2, MagicMock()) is False
    buy_goods.assert_not_awaited()


@pytest.mark.asyncio
async def test_prompt_purchase_skips_prompt_when_vimcoin_short(monkeypatch: pytest.MonkeyPatch) -> None:
    """VimCoin 不足时不发送购买询问"""
    from nonebot_plugin_shop import utils

    prompt = AsyncMock(return_value=True)
    monkeypatch.setattr(utils, "get_user", AsyncMock(return_value=_FakeUser(1)))
    monkeypatch.setattr(utils, "prompt", prompt)

    assert await utils.prompt_purchase("10", "moonlark:dice", 2, MagicMock()) is False
    prompt.assert_not_awaited()


@pytest.mark.asyncio
async def test_buy_goods_adds_items_and_deducts_vimcoin(monkeypatch: pytest.MonkeyPatch) -> None:
    """buy_goods 按商店单价扣费并把商品放入背包"""
    from nonebot_plugin_shop import utils

    user = _FakeUser(100)
    monkeypatch.setattr(utils, "get_user", AsyncMock(return_value=user))

    assert await utils.buy_goods("buy-user-1", "moonlark:dice", 2) == {"moonlark:dice": 2}
    assert user.vimcoin == 40
    assert await utils.get_goods_count("buy-user-1", "moonlark:dice") == 2


@pytest.mark.asyncio
async def test_buy_goods_returns_none_when_vimcoin_short(monkeypatch: pytest.MonkeyPatch) -> None:
    """VimCoin 不足时不给出物品"""
    from nonebot_plugin_shop import utils

    monkeypatch.setattr(utils, "get_user", AsyncMock(return_value=_FakeUser(10)))

    assert await utils.buy_goods("buy-user-2", "moonlark:dice", 1) is None
    assert await utils.get_goods_count("buy-user-2", "moonlark:dice") == 0


@pytest.mark.asyncio
async def test_consume_dice_retries_after_purchase(monkeypatch: pytest.MonkeyPatch) -> None:
    """/roll 在购买骰子后重新尝试扣除"""
    from nonebot_plugin_bag.utils.reduce import ItemNotEnough

    import nonebot_plugin_roll.__main__ as module

    calls = 0

    async def fake_remove(_user_id: str, _location: object, _count: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ItemNotEnough(3, 1, "10")

    offer = AsyncMock(return_value=True)
    monkeypatch.setattr(module, "remove_item_from_bag", fake_remove)
    monkeypatch.setattr(module, "offer_purchase_when_short", offer)

    assert await module.consume_dice("10", 3, MagicMock()) is None
    assert calls == 2
    offer.assert_awaited_once()


@pytest.mark.asyncio
async def test_consume_dice_reports_error_when_not_purchased(monkeypatch: pytest.MonkeyPatch) -> None:
    """用户未购买时沿用原有的「骰子不足」提示"""
    from nonebot_plugin_bag.utils.reduce import ItemNotEnough

    import nonebot_plugin_roll.__main__ as module

    async def fake_remove(_user_id: str, _location: object, _count: int) -> None:
        raise ItemNotEnough(3, 1, "10")

    monkeypatch.setattr(module, "remove_item_from_bag", fake_remove)
    monkeypatch.setattr(module, "offer_purchase_when_short", AsyncMock(return_value=False))

    error = await module.consume_dice("10", 3, MagicMock())
    assert isinstance(error, ItemNotEnough)
    assert (error.need, error.have) == (3, 1)


@pytest.mark.asyncio
async def test_throw_eggs_retries_after_purchase(monkeypatch: pytest.MonkeyPatch) -> None:
    """/splat 在购买鸡蛋后重新尝试扣除并记录攻击"""
    from sqlalchemy import func, select

    from nonebot_plugin_bag.models import Bag
    from nonebot_plugin_orm import get_session
    from nonebot_plugin_eggstrike.models import AttackRecord

    import nonebot_plugin_eggstrike.__main__ as module

    async def fake_offer(user_id: str, item_id: str, count: int, _bot: object) -> bool:
        async with get_session() as session:
            session.add(Bag(user_id=user_id, item_id=item_id, count=count, bag_index=1, data="{}", locked=False))
            await session.commit()
        return True

    monkeypatch.setattr(module, "offer_purchase_when_short", fake_offer)

    assert await module.throw_eggs("splat-user-1", "splat-target-1", "egg", 3, MagicMock()) is None
    async with get_session() as session:
        total = await session.scalar(
            select(func.sum(AttackRecord.count)).where(AttackRecord.user_id == "splat-user-1"),
        )
    assert total == 3


@pytest.mark.asyncio
async def test_throw_eggs_reports_held_count_when_not_purchased(monkeypatch: pytest.MonkeyPatch) -> None:
    """未购买鸡蛋时返回当前持有数量，由调用方提示"""
    import nonebot_plugin_eggstrike.__main__ as module

    monkeypatch.setattr(module, "offer_purchase_when_short", AsyncMock(return_value=False))

    assert await module.throw_eggs("splat-user-2", "splat-target-1", "egg", 3, MagicMock()) == 0


@pytest.mark.asyncio
async def test_throw_eggs_skips_purchase_for_rotten_egg(monkeypatch: pytest.MonkeyPatch) -> None:
    """臭鸡蛋不在商店出售，不应触发购买询问"""
    import nonebot_plugin_eggstrike.__main__ as module
    from nonebot_plugin_shop.utils import offer_purchase_when_short

    prompt_purchase = AsyncMock(return_value=True)
    monkeypatch.setattr("nonebot_plugin_shop.utils.prompt_purchase", prompt_purchase)
    monkeypatch.setattr(module, "offer_purchase_when_short", offer_purchase_when_short)

    assert await module.throw_eggs("splat-user-3", "splat-target-1", "rotten_egg", 1, MagicMock()) == 0
    prompt_purchase.assert_not_awaited()
