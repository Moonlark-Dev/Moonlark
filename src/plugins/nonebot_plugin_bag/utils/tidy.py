from ...nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import lang
from ..exceptions import ItemLockedError
from ..item import BagItem
from .item import get_bag_items


async def get_item_list(user_id: str = get_user_id()) -> list[BagItem]:
    try:
        return await get_bag_items(user_id)
    except ItemLockedError:
        await lang.finish("tidy.item_locked", user_id, reply_message=True, at_sender=False)
    return []
