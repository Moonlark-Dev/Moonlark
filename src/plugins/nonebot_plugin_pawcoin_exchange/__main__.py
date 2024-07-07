from typing import Literal
from nonebot_plugin_alconna import Alconna, Args, Match, Option, on_alconna
from nonebot_plugin_orm import get_session

from .lang import lang

from .models import Exchanged
from ..nonebot_plugin_bag.utils.reduce import ALL, ItemNotEnough, get_bag_item_count, remove_item_from_bag
from ..nonebot_plugin_items.items.moonlark.pawcoin import get_location
from .utils.count import add_exchanged_count
from .utils.exchange import get_exchange_data, get_exchange_vimcoin
from ..nonebot_plugin_larkuser.utils.vimcoin import add_vimcoin
from .utils.item import get_target_item
from ..nonebot_plugin_bag.exceptions import ItemLockedError
from ..nonebot_plugin_bag.utils.item import get_bag_items
from ..nonebot_plugin_larkutils.user import get_user_id


alc = Alconna("pcc", Option("-b|--bag", Args["index", int]), Args["count?", int | Literal["all", "*"]])
pcc = on_alconna(alc)


async def exchange(index: Match[int], count: int, user_id: str) -> None:
    if count < 0:
        await lang.finish("count.invalid_count", user_id)
    elif index.available and count >= 0:
        target_item = await get_target_item(index.result, count, user_id)
        count = count or target_item.stack.count
        target_item.stack.count -= count
        await add_vimcoin(user_id, vimcoin_count := await get_exchange_vimcoin(count))
        await add_exchanged_count(user_id, count, vimcoin_count)
        await lang.finish("pcc.ok", count, vimcoin_count)
    try:
        await remove_item_from_bag(user_id, get_location(), count or ALL)
    except ItemLockedError:
        await lang.finish("bag_error.locked", user_id)
    except ItemNotEnough as e:
        await lang.finish("bag_error.not_enough_item", user_id, e.have)
    await add_vimcoin(user_id, vimcoin_count := await get_exchange_vimcoin(count))
    await add_exchanged_count(user_id, count, vimcoin_count)
    await lang.finish("pcc.ok", count, vimcoin_count)


@pcc.handle()
async def _(index: Match[int], count: Match[int | Literal["all", "*"]], user_id: str = get_user_id()) -> None:
    if count.available:
        await exchange(index, count.result if isinstance(count.result, int) else 0, user_id)
    async with get_session() as session:
        data = await session.get(Exchanged, user_id)
        if data is not None:
            exchanged_pawcoin = data.pawcoin
            got_vimcoin = data.vimcoin
        else:
            exchanged_pawcoin = 0
            got_vimcoin = 0
    await lang.finish(
        "pcc.info",
        user_id,
        await get_exchange_data(),
        exchanged_pawcoin,
        got_vimcoin,
        await get_bag_item_count(await get_bag_items(user_id), get_location()),
    )
