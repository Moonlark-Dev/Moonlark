from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_consumable_items_registered() -> None:
    from nonebot_plugin_items.base.consumable import ConsumableItem
    from nonebot_plugin_items.items.moonlark.cake import Cake
    from nonebot_plugin_items.items.moonlark.milk import Milk
    from nonebot_plugin_items.items.moonlark.rotten_egg import RottenEgg

    assert isinstance(Milk, type) and issubclass(Milk, ConsumableItem)
    assert issubclass(Cake, ConsumableItem)
    assert not issubclass(RottenEgg, ConsumableItem)


@pytest.mark.asyncio
async def test_milk_detaches_negative_buff() -> None:
    """牛奶有概率（这里是 mock 必定命中）消除一个随机的负面 buff"""
    from unittest.mock import patch

    from nonebot_plugin_buff import attach_buff, get_buff_layers
    from nonebot_plugin_buff.builtin import BAD_LUCK_BUFF_ID

    from nonebot_plugin_items.base.stack import ItemStack
    from nonebot_plugin_items.registry import ITEMS
    from nonebot_plugin_items.registry.registry import ResourceLocation
    from nonebot_plugin_items.items.moonlark.milk import Milk

    # 准备 2 层霉运
    await attach_buff("milk-user", BAD_LUCK_BUFF_ID, layers=2)
    assert await get_buff_layers("milk-user", BAD_LUCK_BUFF_ID) == 2

    milk: Milk = ITEMS.getValue(ResourceLocation("moonlark", "milk"))
    stack = ItemStack(milk, 1, {}, "milk-user")

    from nonebot_plugin_buff import api as buff_api

    # random() = 0 一定命中 90% 的生效概率
    with patch("random.random", return_value=0.0):
        with patch.object(buff_api, "choice", lambda items: items[0]):
            message = await milk.on_use(stack)

    assert "霉运" in message
    assert await get_buff_layers("milk-user", BAD_LUCK_BUFF_ID) == 1

    # 没有负面 buff 时提示无效果
    await attach_buff("milk-user2", BAD_LUCK_BUFF_ID, layers=1)
    with patch("random.random", return_value=0.0):
        with patch.object(buff_api, "detach_random_negative_buff", AsyncMock(return_value=None)):
            message = await milk.on_use(ItemStack(milk, 1, {}, "milk-user2"))
    assert message == await milk.getText("milk.use_none", "milk-user2")

    # 未命中 90% 概率时什么都不会发生（霉运会降低生效概率）
    await attach_buff("milk-user3", BAD_LUCK_BUFF_ID, layers=1)
    with patch("random.random", return_value=1.0):
        message = await milk.on_use(ItemStack(milk, 1, {}, "milk-user3"))
    assert message == await milk.getText("milk.use_none", "milk-user3")
    assert await get_buff_layers("milk-user3", BAD_LUCK_BUFF_ID) == 1


@pytest.mark.asyncio
async def test_cake_heals_full(monkeypatch: pytest.MonkeyPatch) -> None:
    """蛋糕吃完回满血"""
    from nonebot_plugin_items.base.stack import ItemStack
    from nonebot_plugin_items.items.moonlark.cake import Cake
    from nonebot_plugin_items.registry import ITEMS
    from nonebot_plugin_items.registry.registry import ResourceLocation

    fake_user = MagicMock()
    fake_user.is_registered.return_value = True
    fake_user.get_health.return_value = 10.0
    fake_user.set_health = AsyncMock()

    import nonebot_plugin_larkuser

    async def fake_get_user(_user_id: str):
        return fake_user

    monkeypatch.setattr(nonebot_plugin_larkuser, "get_user", fake_get_user)

    cake: Cake = ITEMS.getValue(ResourceLocation("moonlark", "cake"))
    assert cake.fav_value == 0.003
    assert cake.daily_gift_limit == 1

    stack = ItemStack(cake, 1, {}, "cake-user")
    message = await cake.on_use(stack)
    fake_user.set_health.assert_awaited_once_with(100)
    assert "回满" in message

    # 已经满血时不会重复治疗
    fake_user.get_health.return_value = 100.0
    message = await cake.on_use(stack)
    assert fake_user.set_health.await_count == 1
    assert "满血" in message

    # 未注册用户无法使用
    fake_user.is_registered.return_value = False
    message = await cake.on_use(stack)
    assert "注册" in message


@pytest.mark.asyncio
async def test_gift_item_daily_limit_default() -> None:
    from nonebot_plugin_items.items.moonlark.gifts.dried_fish import DriedFish

    assert DriedFish.daily_gift_limit == 0


@pytest.mark.asyncio
async def test_buff_registry_is_negative() -> None:
    from nonebot_plugin_buff.builtin import BAD_LUCK
    from nonebot_plugin_buff.registry import get_buff_definition

    definition = get_buff_definition(BAD_LUCK.id)
    assert definition is not None and definition.is_negative is True


@pytest.mark.asyncio
async def test_detach_random_negative_buff() -> None:
    from nonebot_plugin_buff.api import detach_random_negative_buff, get_buff_layers
    from nonebot_plugin_buff.builtin import BAD_LUCK_BUFF_ID, attach_buff

    # 无负面 buff 时返回 None
    assert await detach_random_negative_buff("no-negative") is None

    await attach_buff("negative-user", BAD_LUCK_BUFF_ID, layers=3)
    attachment = await detach_random_negative_buff("negative-user")
    assert attachment is not None and attachment.buff_id == BAD_LUCK_BUFF_ID
    # 多层只移除一层
    assert await get_buff_layers("negative-user", BAD_LUCK_BUFF_ID) == 2


@pytest.mark.asyncio
async def test_shop_has_milk_and_barrier() -> None:
    from nonebot_plugin_shop.goods import GOODS, GOODS_CATEGORIES

    consumable_ids = [item_id for item_id, _ in GOODS_CATEGORIES["consumable"]]
    assert "moonlark:milk" in consumable_ids
    equipment_ids = [item_id for item_id, _ in GOODS_CATEGORIES["equipment"]]
    assert "moonlark:temp_barrier" in equipment_ids
    # 全量商品表保持跨分类的连续编号，并包含所有分类的商品
    assert GOODS[-2:] == [("moonlark:milk", 35), ("moonlark:temp_barrier", 150)]
    assert len(GOODS) == sum(len(items) for items in GOODS_CATEGORIES.values())


@pytest.mark.asyncio
async def test_egg_types_include_ex() -> None:
    from nonebot_plugin_eggstrike.utils import EGG_TYPES, ROTTEN_EGG_EX_TYPE

    assert ROTTEN_EGG_EX_TYPE in EGG_TYPES
    ex = EGG_TYPES[ROTTEN_EGG_EX_TYPE]
    assert ex.damage == 2.0
    assert ex.buff_hours == 6
    assert ex.explode_chance == 0.03
    assert EGG_TYPES["rotten_egg"].explode_chance == 0.01
    assert EGG_TYPES["egg"].explode_chance == 0.0


@pytest.mark.asyncio
async def test_roll_hand_explosion(monkeypatch: pytest.MonkeyPatch) -> None:
    import nonebot_plugin_eggstrike.utils as utils

    monkeypatch.setattr(utils, "random", lambda: 0.02)
    # 0.02 < 0.03：臭鸡蛋 Ex 会爆炸；0.02 > 0.01：臭鸡蛋不会爆炸
    assert utils.roll_hand_explosion("rotten_egg_ex", 10) == 10
    assert utils.roll_hand_explosion("rotten_egg", 10) == 0
    assert utils.roll_hand_explosion("egg", 10) == 0
