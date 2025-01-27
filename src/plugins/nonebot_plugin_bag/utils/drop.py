from nonebot.params import Depends
from nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import lang
from ..exceptions import ItemLockedError
from ..item import BagItem
from .item import get_bag_item


async def get_target_item(index: int, user_id: str = get_user_id()) -> BagItem:
    """获取用户想要丢弃的物品（请使用依赖注入）"""
    try:
        item = await get_bag_item(user_id, index)
    except IndexError:
        await lang.finish("show.index_error", user_id, reply_message=True, at_sender=False)
    except ItemLockedError:
        await lang.finish("drop.item_locked", user_id, reply_message=True, at_sender=False)
    if not item.stack.getNbt("droppable", True):
        await lang.finish("drop.item_not_droppable", user_id, reply_message=True, at_sender=False)
    return item


def get_count(count: int, item: BagItem = Depends(get_target_item)) -> int:
    if count <= 0:
        return item.stack.count
    return min(count, item.stack.count)
