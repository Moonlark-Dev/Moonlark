import random

from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna
from nonebot_plugin_alconna.uniseg import UniMessage

from nonebot_plugin_bag.utils.bag import give_item
from nonebot_plugin_items.utils.get import get_item
from nonebot_plugin_items.utils.string import get_location_by_id
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkuser import get_user, patch_matcher
from nonebot_plugin_larkutils import get_user_id

from .goods import GOODS, GOODS_ALTERNATIVES

alc = Alconna(
    "shop",
    Subcommand("buy", Args["index", int], Args["count", int, 1]),
)
shop = on_alconna(alc)
patch_matcher(shop)
lang = LangHelper()


async def get_goods_name(item_id: str, user_id: str) -> str:
    location = get_location_by_id(item_id)
    stack = await get_item(location, user_id)
    return await stack.getName()


async def build_markdown_list(user_id: str, vimcoin: float) -> str:
    """构建 QQ 官方机器人的商店列表 markdown。

    商品条目使用 <qqbot-cmd-input>：点击即把 `{前缀}shop buy <编号> 1` 填入输入框，
    编号只用于拼装指令，不展示在商品文本中。
    """
    items = []
    for index, (item_id, price) in enumerate(GOODS, start=1):
        name = await get_goods_name(item_id, user_id)
        items.append(await lang.text("list.item_md", user_id, index, name, price))
    return "\n".join(
        [
            await lang.text("list.title_md", user_id, vimcoin),
            "",
            *items,
            "",
            await lang.text("list.footer_md", user_id),
        ],
    )


@shop.assign("$main")
async def handle_main(bot: Bot, user_id: str = get_user_id()) -> None:
    user = await get_user(user_id)
    vimcoin = round(user.get_vimcoin(), 1)
    if isinstance(bot, QQBot):
        await UniMessage().style(await build_markdown_list(user_id, vimcoin), "markdown").send()
        await shop.finish()

    lines = [await lang.text("list.title", user_id, vimcoin)]
    for index, (item_id, price) in enumerate(GOODS, start=1):
        name = await get_goods_name(item_id, user_id)
        lines.append(await lang.text("list.item", user_id, index, name, price))
    lines.append(await lang.text("list.footer", user_id))
    await shop.finish("\n".join(lines))


@shop.assign("buy")
async def handle_buy(index: int, count: int = 1, user_id: str = get_user_id()) -> None:
    if not 1 <= index <= len(GOODS):
        await lang.finish("buy.invalid_index", user_id)
    if count <= 0:
        await lang.finish("buy.invalid_count", user_id)

    item_id, price = GOODS[index - 1]
    total_price = price * count
    name = await get_goods_name(item_id, user_id)

    user = await get_user(user_id)
    if not await user.use_vimcoin(total_price):
        await lang.finish("buy.no_enough_vimcoin", user_id, total_price, round(user.get_vimcoin(), 1))

    location = get_location_by_id(item_id)
    alternatives = GOODS_ALTERNATIVES.get(item_id)
    if not alternatives:
        stack = await get_item(location, user_id, count)
        await give_item(user_id, stack)
        await lang.finish("buy.success", user_id, name, count, total_price)

    # 逐单位随机判定：例如买鸡蛋时有概率获得臭鸡蛋
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

    if got.get(item_id, 0) == count:
        await lang.finish("buy.success", user_id, name, count, total_price)

    parts = []
    for got_id, got_count in got.items():
        got_name = await get_goods_name(got_id, user_id)
        parts.append(await lang.text("buy.item_part", user_id, got_name, got_count))
    await lang.finish("buy.success_alt", user_id, "、".join(parts), total_price)
