from nonebot_plugin_alconna import UniMessage
from datetime import datetime, timedelta

from nonebot_plugin_orm import get_session

from ...types import OverflowItem

from ...utils.bag import give_item


from ...utils.overflow import get_overflow_item, is_item_takeable
from ....nonebot_plugin_larkutils.user import get_user_id
from ...__main__ import bag
from ...__main__ import lang
from ...config import config


@bag.assign("overflow.get")
async def _(index: int, count: int, user_id: str = get_user_id()) -> None:
    try:
        item = await get_overflow_item(index)
    except IndexError:
        await lang.finish("overflow_show.not_found", user_id)
    if is_item_takeable(user_id, index):
        count = min(max(0, count), item["item"].count)
        if item["item"].count - count <= 0:
            async with get_session() as session:
                i = await session.get(OverflowItem, item["index"])
                if i is not None:
                    await session.delete(i)
                    await session.commit()
        item["item"].count = count
        await give_item(user_id, item["item"])
        await lang.finish("overflow_get.done", user_id)
    else:
        await lang.finish("overflow_get.failed", user_id)
