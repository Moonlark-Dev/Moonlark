import json

from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna
from nonebot_plugin_alconna.uniseg import UniMessage
from sqlalchemy import select

from nonebot_plugin_bag.exceptions import ItemLockedError
from nonebot_plugin_bag.utils.bag import get_bag_item, give_item
from nonebot_plugin_items.base.stack import ItemStack
from nonebot_plugin_items.utils.get import get_item
from nonebot_plugin_items.utils.string import get_location_by_id
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkuser import get_user, patch_matcher
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_orm import AsyncSession, get_session

from .models import MarketItem, SellLog

lang = LangHelper()
matcher = on_alconna(
    Alconna(
        "market",
        Subcommand("sell", Args["bag_index", int], Args["count", int, 0], Args["price", str, ""]),
        Subcommand("buy", Args["name", str], Args["count", int, 1]),
        Subcommand("list", Args["page", int, 1]),
    ),
)
patch_matcher(matcher)

# 每页展示的商品数量
ITEMS_PER_PAGE = 10
# 成交手续费，卖家实际获得 (1 - SELL_FEE_RATE)
SELL_FEE_RATE = 0.01
# price 参数中最多生效的 +/- 数量（每个符号浮动 1%）
MAX_PRICE_DIFF = 5


async def get_average_price(item: ItemStack, session: AsyncSession) -> float | None:
    """获取物品的基准单价

    优先使用 SellLog 中记录的平均成交价；没有成交记录时退回物品 NBT 中的 `price`；
    两者都没有时返回 None，表示需要卖家自行指定固定单价。
    """
    result = await session.get(SellLog, str(item.item.getLocation()))
    if result is not None and result.sold_count > 0:
        return round(result.price_sum / result.sold_count, 2)
    nbt_price = item.getNbt("price")
    if nbt_price is None:
        return None
    try:
        price = round(float(nbt_price), 2)
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def resolve_unit_price(price: str, base_price: float | None) -> float | None:
    """解析 `market sell` 的 price 参数，返回上架单价

    - 留空：使用基准价（平均成交价或物品 NBT 价格），没有基准价时返回 None
    - 连续的 + / -：在基准价基础上浮动 1% × 符号数量（最多 MAX_PRICE_DIFF 个），没有基准价时返回 None
    - 数字：作为固定单价，必须为正数

    Raises:
        ValueError: 参数既不是连续的 +/-、也不是正数
    """
    price = price.strip()
    if not price:
        return base_price
    if price[0] in "+-" and len(set(price)) == 1:
        if base_price is None:
            return None
        rate = 0.01 * min(MAX_PRICE_DIFF, len(price))
        return round(base_price * (1 + rate if price[0] == "+" else 1 - rate), 2)
    try:
        unit_price = round(float(price), 2)
    except ValueError as e:
        raise ValueError(f"invalid price: {price}") from e
    if unit_price <= 0:
        raise ValueError(f"price must be positive: {price}")
    return unit_price


async def get_market_item(user_id: str, data: MarketItem) -> ItemStack:
    """按上架记录还原物品，user_id 仅用于名称本地化"""
    location = get_location_by_id(data.item_namespace)
    return await get_item(location, user_id, data.remain_count, json.loads(data.item_data))


async def find_market_items(user_id: str, session: AsyncSession, keyword: str) -> list[MarketItem]:
    """查找在售商品

    keyword 为纯数字时按商品编号（item_id）精确匹配，否则按物品名称模糊匹配。
    """
    keyword = keyword.strip()
    if keyword.isdigit():
        data = await session.get(MarketItem, int(keyword))
        return [data] if data is not None and data.remain_count > 0 else []
    items = []
    for data in await session.scalars(
        select(MarketItem).where(MarketItem.remain_count > 0).order_by(MarketItem.item_id),
    ):
        stack = await get_market_item(user_id, data)
        if keyword in await stack.getName():
            items.append(data)
    return items


async def give_market_item(count: int, data: MarketItem, user_id: str) -> None:
    """把成交的物品发放给买家"""
    item = await get_market_item(user_id, data)
    item.count = count
    await give_item(user_id, item)


async def record_sell(session: AsyncSession, item_namespace: str, count: int, unit_price: float) -> None:
    """记录成交，用于后续计算平均成交价"""
    result = await session.get(SellLog, item_namespace)
    if result is None:
        session.add(SellLog(item_namespace=item_namespace, sold_count=count, price_sum=unit_price * count))
        # 同一物品可能在同一笔购买中出现多条上架记录，先落库让后续查询可见
        await session.flush()
        return
    result.sold_count += count
    result.price_sum += unit_price * count


async def build_text_list(
    user_id: str,
    page: int,
    total_pages: int,
    total: int,
    items: list[tuple[MarketItem, str]],
) -> str:
    """构建纯文本商品列表（非 QQ 平台）"""
    lines = [await lang.text("list.title", user_id, page, total_pages, total)]
    for data, name in items:
        lines.append(await lang.text("list.item", user_id, data.item_id, name, data.remain_count, data.price))
    lines.append(await lang.text("list.footer", user_id))
    return "\n".join(lines)


async def build_markdown_list(
    user_id: str,
    page: int,
    total_pages: int,
    total: int,
    items: list[tuple[MarketItem, str]],
) -> str:
    """构建 QQ 官方机器人的市场列表 markdown

    商品条目使用 <qqbot-cmd-input>：点击即把 `{前缀}market buy <编号> 1` 填入输入框，
    编号（item_id）与 `market list` 中展示的编号一致。
    """
    lines = [await lang.text("list.title_md", user_id, page, total_pages, total), ""]
    for data, name in items:
        lines.append(await lang.text("list.item_md", user_id, data.item_id, name, data.remain_count, data.price))
    lines.extend(["", await lang.text("list.footer_md", user_id)])
    return "\n".join(lines)


@matcher.assign("$main")
async def handle_market_main(user_id: str = get_user_id()) -> None:
    async with get_session() as session:
        count = len((await session.scalars(select(MarketItem).where(MarketItem.remain_count > 0))).all())
    await lang.finish("main.info", user_id, count)


@matcher.assign("sell")
async def handle_market_sell(bag_index: int, count: int, price: str, user_id: str = get_user_id()) -> None:
    try:
        item = await get_bag_item(user_id, bag_index)
    except IndexError:
        await lang.finish("sell.index_error", user_id)
    except ItemLockedError:
        await lang.finish("sell.item_locked", user_id)
    if count < 0:
        await item.unlock_item()
        await lang.finish("sell.wrong_count", user_id)
    count = count or item.stack.count
    if count > item.stack.count:
        await item.unlock_item()
        await lang.finish("sell.item_not_enough", user_id, item.stack.count)
    item_name = await item.stack.getName()
    async with get_session() as session:
        base_price = await get_average_price(item.stack, session)
    try:
        unit_price = resolve_unit_price(price, base_price)
    except ValueError:
        await item.unlock_item()
        await lang.finish("sell.wrong_price", user_id)
    if unit_price is None:
        await item.unlock_item()
        await lang.finish("sell.no_base_price", user_id)
    async with get_session() as session:
        session.add(
            MarketItem(
                user_id=user_id,
                remain_count=count,
                item_data=json.dumps(item.stack.data),
                price=unit_price,
                item_namespace=str(item.stack.item.getLocation()),
            ),
        )
        await session.commit()
    # 上架成功后从背包中扣除物品（物品在 get_bag_item 时已被锁定，on_delete 会保存并解锁）
    item.stack.count -= count
    await item.on_delete()
    await lang.finish("sell.done", user_id, count, item_name, unit_price)


@matcher.assign("buy")
async def handle_market_buy(name: str, count: int, user_id: str = get_user_id()) -> None:
    if count <= 0:
        await lang.finish("buy.wrong_count", user_id)
    user = await get_user(user_id)
    bought_count = 0
    used_vimcoin = 0.0
    async with get_session() as session:
        market_items = await find_market_items(user_id, session, name)
        if not market_items:
            await lang.finish("buy.not_found", user_id, name)
        for data in market_items:
            if bought_count >= count:
                break
            take = min(count - bought_count, data.remain_count)
            if data.price > 0:
                take = min(take, int(user.get_vimcoin() // data.price))
            if take <= 0:
                continue
            total_price = round(data.price * take, 2)
            if not await user.has_vimcoin(total_price):
                continue
            await user.use_vimcoin(total_price)
            await (await get_user(data.user_id)).add_vimcoin(round(total_price * (1 - SELL_FEE_RATE), 2))
            await give_market_item(take, data, user_id)
            await record_sell(session, data.item_namespace, take, data.price)
            data.remain_count -= take
            if data.remain_count <= 0:
                await session.delete(data)
            bought_count += take
            used_vimcoin += total_price
        await session.commit()
    if bought_count == 0:
        await lang.finish("buy.no_enough_vimcoin", user_id)
    await lang.finish("buy.finish", user_id, bought_count, name, round(used_vimcoin, 2))


@matcher.assign("list")
async def handle_market_list(bot: Bot, page: int, user_id: str = get_user_id()) -> None:
    page = max(1, page)
    async with get_session() as session:
        all_items = (
            await session.scalars(select(MarketItem).where(MarketItem.remain_count > 0).order_by(MarketItem.item_id))
        ).all()
        total = len(all_items)
        if total == 0:
            await lang.finish("list.empty", user_id)
        total_pages = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        page = min(page, total_pages)
        start = (page - 1) * ITEMS_PER_PAGE
        page_items = []
        for data in all_items[start : start + ITEMS_PER_PAGE]:
            item = await get_market_item(user_id, data)
            page_items.append((data, await item.getName()))
    if isinstance(bot, QQBot):
        await UniMessage().style(
            await build_markdown_list(user_id, page, total_pages, total, page_items),
            "markdown",
        ).send()
        await matcher.finish()
    await matcher.finish(await build_text_list(user_id, page, total_pages, total, page_items))
