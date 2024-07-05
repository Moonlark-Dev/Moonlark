from ..utils.overflow import put_overflow_item
from ..utils.drop import get_target_item
from ..utils.drop import get_count
from ..item import BagItem
from ...nonebot_plugin_larkutils.user import get_user_id
from ...nonebot_plugin_item.utils.get import get_item
from ..__main__ import lang, bag
from nonebot.params import Depends


@bag.assign("drop")
async def _(
    count: int = Depends(get_count), item: BagItem = Depends(get_target_item), user_id: str = get_user_id()
) -> None:
    """丢弃物品"""
    item.stack.count -= count
    await put_overflow_item(await get_item(item.stack.item.getLocation(), user_id, count, item.stack.data))
    await lang.finish("drop.success", user_id, count, await item.stack.getName(), item.stack.count)
