from typing import Literal
from nonebot_plugin_alconna import Alconna, Args, Match, Option, on_alconna
from nonebot_plugin_orm import get_session

from .utils.exchange import exchange
from .lang import lang
from .models import Exchanged
from ..nonebot_plugin_bag.utils.reduce import get_bag_item_count
from ..nonebot_plugin_items.items.moonlark.pawcoin import get_location
from .utils.exchange import get_exchange_data
from ..nonebot_plugin_bag.utils.item import get_bag_items
from ..nonebot_plugin_larkutils.user import get_user_id


alc = Alconna("pcc", Option("-b|--bag", Args["index", int]), Args["count?", int | Literal["all", "*"]])
pcc = on_alconna(alc)


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
