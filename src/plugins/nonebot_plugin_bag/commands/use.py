from typing import Any

from nonebot_plugin_alconna import UniMessage
from ..exceptions import ItemLockedError
from ..utils.item import get_bag_item
from ...nonebot_plugin_larkutils.user import get_user_id
from ..item import BagItem
from ..__main__ import bag, lang
from nonebot.params import Depends


async def get_item(index: int, user_id: str = get_user_id()) -> BagItem:
    """获取用户想要使用的物品（请使用依赖注入）"""
    try:
        return await get_bag_item(user_id, index)
    except IndexError:
        await lang.finish("show.index_error", user_id, reply_message=True, at_sender=False)
    except ItemLockedError:
        await lang.finish("drop.item_locked", user_id, reply_message=True, at_sender=False)
    raise


@bag.assign("use")
async def _(args: list[Any], count: int, item: BagItem = Depends(get_item), user_id: str = get_user_id()) -> None:
    if 0 < count < item.stack.count:
        await lang.finish("use.not_enough", user_id, item.stack.count)
    elif item.stack.item.getProperties()["multi_use"] and count != 1:
        await lang.finish("use.unsupported_count", user_id)
    elif not item.stack.isUseable():
        await lang.finish("use.not_useable", user_id)
    ret = await item.stack.use(*args, count=count)
    if isinstance(ret, str) or isinstance(ret, UniMessage):
        await bag.finish(ret)
