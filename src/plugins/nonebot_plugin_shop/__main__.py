from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna

from nonebot_plugin_bag.utils.bag import give_item
from nonebot_plugin_items.utils.get import get_item
from nonebot_plugin_items.utils.string import get_location_by_id
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkuser import get_user, patch_matcher
from nonebot_plugin_larkutils import get_user_id

from .goods import GOODS

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


@shop.assign("$main")
async def handle_main(user_id: str = get_user_id()) -> None:
    user = await get_user(user_id)
    lines = [await lang.text("list.title", user_id, round(user.get_vimcoin(), 1))]
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
    stack = await get_item(location, user_id, count)
    await give_item(user_id, stack)

    await lang.finish("buy.success", user_id, name, count, total_price)
