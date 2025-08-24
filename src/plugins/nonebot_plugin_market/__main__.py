import json
from nonebot_plugin_alconna import Alconna, on_alconna, Args, Subcommand
from nonebot_plugin_items.base.stack import ItemStack
from nonebot_plugin_items.utils.get import get_item
from nonebot_plugin_items.utils.string import get_location_by_id
from nonebot_plugin_larkuser.utils.user import get_user
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_bag.utils.bag import get_bag_item, give_item
from nonebot_plugin_orm import get_session, AsyncSession
from .models import MarketItem, SellLog
from sqlalchemy import select


lang = LangHelper()
matcher = on_alconna(
    Alconna(
        "market",
        Subcommand("sell", Args["bag_index", int], Args["count", int, 0], Args["price_diff", str, ""]),
        Subcommand("buy", Args["name", str], Args["count", int, 1]),
    )
)


async def get_average_price(item_data: ItemStack, session: AsyncSession) -> float:
    result = await session.get(SellLog, {"item_namespace": str(item_data.item.getLocation())})
    if result is not None:
        return round(result.price_sum / result.sold_count, 2)
    if (p := item_data.getNbt("price")) is not None:
        return p
    raise TypeError


@matcher.assign("$main")
async def _(user_id: str = get_user_id()) -> None:
    async with get_session() as session:
        count = len((await session.scalars(select(MarketItem).where(MarketItem.remain_count > 0))).all())
    await lang.finish("main.info", user_id, count)


@matcher.assign("sell")
async def _(bag_index: int, count: int, price_diff: str, user_id: str = get_user_id()) -> None:
    try:
        item = await get_bag_item(user_id, bag_index)
    except IndexError:
        await lang.finish("sell.index_error", user_id)
    if count > 0 and item.stack.count < count:
        await lang.finish("sell.item_not_enough", user_id, item.stack.count)
    elif count < 0:
        await lang.finish("sell.wrong_count", user_id)
    elif count == 0:
        count = item.stack.count
    async with get_session() as session:
        try:
            avg_price = await get_average_price(item.stack, session)
        except TypeError:
            await lang.finish("sell.not_soldable", user_id)
        if price_diff.startswith("+"):
            price = round(avg_price * (1 + 0.01 * min(5, len(price_diff))), 2)
        elif price_diff.startswith("-"):
            price = round(avg_price * (1 - 0.01 * min(5, len(price_diff))), 2)
        else:
            price = avg_price
        session.add(
            MarketItem(
                user_id=user_id,
                remain_count=count,
                item_data=json.dumps(item.stack.data).encode("utf-8"),
                price=price,
                item_namespace=str(item.stack.item.getLocation()),
            )
        )
        await session.commit()
    item.stack.count -= count
    await lang.finish("sell.done", user_id, item.stack.getName(), count, price)


async def get_market_item(user_id: str, data: MarketItem) -> ItemStack:
    location = get_location_by_id(data.item_namespace)
    return await get_item(location, user_id, data.remain_count, json.loads(data.item_data))


async def get_market_items_by_name(user_id: str, session: AsyncSession, name: str) -> list[MarketItem]:
    items = []
    for item_data in await session.scalars(select(MarketItem).where(MarketItem.remain_count > 0)):
        item = await get_market_item(user_id, item_data)
        if name in await item.getName():
            items.append(item_data)
    return items


async def give_market_item(count: int, item_data: MarketItem, user_id: str) -> None:
    item = await get_market_item(user_id, item_data)
    item.count = count
    await give_item(user_id, item)


@matcher.assign("buy")
async def _(name: str, count: int, user_id: str = get_user_id()) -> None:
    bought_count = 0
    used_vimcoin = 0
    user = await get_user(user_id)
    async with get_session() as session:
        items = await get_market_items_by_name(user_id, session, name)
        for item in items:
            if item.remain_count >= (c := count - bought_count) and await user.has_vimcoin(p := item.price * c):
                bought_count = count
                await user.use_vimcoin(p, True)
                await (await get_user(item.user_id)).add_vimcoin(p * 0.99)
                await give_market_item(c, item, user_id)
                item.remain_count -= c
                used_vimcoin += p
                break
            elif user.has_vimcoin(p := item.price * item.remain_count):
                bought_count += item.remain_count
                await user.use_vimcoin(p, True)
                await (await get_user(item.user_id)).add_vimcoin(p * 0.99)
                await give_market_item(item.remain_count, item, user_id)
                await session.delete(item)
                used_vimcoin += p
        await session.commit()
    await lang.finish("buy.finish", user_id, p, bought_count, name)
