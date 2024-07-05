from ..utils.drop import get_item
from ..utils.drop import get_count
from ..item import BagItem
from ...nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import lang, bag
from nonebot.params import Depends


@bag.assign("drop")
async def _(count: int = Depends(get_count), item: BagItem = Depends(get_item), user_id: str = get_user_id()) -> None:
    """丢弃物品"""
    item.stack.count -= count
    await lang.finish("drop.success", user_id, count, await item.stack.getName(), item.stack.count)
