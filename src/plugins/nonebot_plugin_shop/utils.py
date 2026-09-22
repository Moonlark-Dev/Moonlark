"""供其它插件复用的商店购买工具。

除了 ``/shop buy`` 本身，其它需要消耗商店商品的插件（如 ``/splat``、``/roll``）
可以在持有数量不足时调用 :func:`offer_purchase_when_short`：先询问用户是否购买缺口，
再按商店规则完成购买，最后重新核对持有量以决定是否继续原操作。
"""

import random

from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Button, UniMessage
from nonebot_plugin_bag.models import Bag
from nonebot_plugin_bag.utils.bag import give_item
from nonebot_plugin_items.utils.get import get_item
from nonebot_plugin_items.utils.string import get_location_by_id
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkuser.utils.waiter import PromptRetryTooMuch, PromptTimeout, prompt
from nonebot_plugin_orm import get_session
from sqlalchemy import func, select

from .goods import GOODS, GOODS_ALTERNATIVES

lang = LangHelper()

# 购买询问中允许的回复，以及被视为「同意购买」的回复
ANSWER_ALIASES = {"y", "yes", "n", "no"}
AGREE_ANSWERS = {"y", "yes"}


def get_goods_price(item_id: str) -> int | None:
    """获取商品单价，商品不在商店出售时返回 None"""
    for goods_id, price in GOODS:
        if goods_id == item_id:
            return price
    return None


async def get_goods_name(item_id: str, user_id: str) -> str:
    """获取商品的显示名称"""
    stack = await get_item(get_location_by_id(item_id), user_id)
    return await stack.getName()


async def get_goods_count(user_id: str, item_id: str) -> int:
    """统计用户背包中指定商品的数量"""
    async with get_session() as session:
        return (
            await session.scalar(
                select(func.coalesce(func.sum(Bag.count), 0)).where(Bag.user_id == user_id, Bag.item_id == item_id),
            )
        ) or 0


async def buy_goods(user_id: str, item_id: str, count: int) -> dict[str, int] | None:
    """按商店规则为用户购买商品。

    与 ``/shop buy`` 行为一致：逐单位随机判定替换物品（例如鸡蛋有概率变成臭鸡蛋）。
    成功时扣除 VimCoin、将物品放入背包并返回各物品的获得数量；
    商品不在商店、数量非法或 VimCoin 不足时返回 None。
    """
    price = get_goods_price(item_id)
    if price is None or count <= 0:
        return None
    user = await get_user(user_id)
    if not await user.use_vimcoin(price * count):
        return None

    alternatives = GOODS_ALTERNATIVES.get(item_id)
    if not alternatives:
        stack = await get_item(get_location_by_id(item_id), user_id, count)
        await give_item(user_id, stack)
        return {item_id: count}

    got: dict[str, int] = {}
    for _ in range(count):
        chosen = item_id
        roll = random.random()
        acc = 0.0
        for probability, alt_id in alternatives:
            acc += probability
            if roll < acc:
                chosen = alt_id
                break
        got[chosen] = got.get(chosen, 0) + 1

    for got_id, got_count in got.items():
        stack = await get_item(get_location_by_id(got_id), user_id, got_count)
        await give_item(user_id, stack)
    return got


async def build_purchase_prompt(item_id: str, count: int, user_id: str, bot: Bot) -> str | UniMessage:
    """构建购买询问消息：QQ 官方机器人使用 markdown 与键盘按钮，其余平台保持文本 [y/n]。"""
    price = get_goods_price(item_id)
    if price is None:
        raise ValueError(f"{item_id} is not sold in shop.")
    name = await get_goods_name(item_id, user_id)
    total_price = price * count
    if isinstance(bot, QQBot):
        return (
            UniMessage()
            .style(await lang.text("purchase.prompt_markdown", user_id, name, count, total_price), "markdown")
            .keyboard(
                Button("enter", await lang.text("purchase.button_yes", user_id), text="y"),
                Button("enter", await lang.text("purchase.button_no", user_id), text="n"),
            )
        )
    return await lang.text("purchase.prompt", user_id, name, count, total_price)


async def prompt_purchase(user_id: str, item_id: str, count: int, bot: Bot) -> bool:
    """询问用户是否购买指定数量的商品，成功购买返回 True。

    商品不在商店、VimCoin 不足、用户拒绝购买或超出回复次数时均返回 False。
    """
    price = get_goods_price(item_id)
    if price is None or count <= 0:
        return False
    user = await get_user(user_id)
    if not await user.has_vimcoin(price * count):
        return False
    try:
        agreed = await prompt(
            await build_purchase_prompt(item_id, count, user_id, bot),
            user_id,
            checker=lambda message: message.strip().lower() in ANSWER_ALIASES,
            retry=1,
            parser=lambda message: message.strip().lower() in AGREE_ANSWERS,
            ignore_error_details=False,
            allow_quit=False,
        )
    except (PromptTimeout, PromptRetryTooMuch):
        return False
    if not agreed:
        return False
    return await buy_goods(user_id, item_id, count) is not None


async def offer_purchase_when_short(user_id: str, item_id: str, count: int, bot: Bot) -> bool:
    """持有量不足时询问用户是否购买缺口数量，返回购买后是否已持有足够数量。

    商品不在商店出售时不询问，直接返回 False，由调用方给出原有的「数量不足」提示；
    已持有足够数量时同样不询问。购买后重新核对持有量：鸡蛋等商品可能被随机替换成
    其它物品，此时仍可能不足，调用方需要再判定一次。
    """
    if get_goods_price(item_id) is None:
        return False
    have = await get_goods_count(user_id, item_id)
    if have >= count:
        return True
    if not await prompt_purchase(user_id, item_id, count - have, bot):
        return False
    return await get_goods_count(user_id, item_id) >= count
