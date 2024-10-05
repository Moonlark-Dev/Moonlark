from typing import Optional
from nonebot.params import Depends
from ...nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import lang
from ..exceptions import ItemLockedError
from ..item import BagItem
from .item import get_bag_item
from nonebot.log import logger


async def get_origin_item(origin: int, user_id: str = get_user_id()) -> BagItem:
    try:
        return await get_bag_item(user_id, origin)
    except ItemLockedError:
        await lang.finish(f"move.origin_locked", user_id)
        logger.warning(traceback.format_exc())
    except IndexError:
        await lang.finish(f"move.origin_index_error", user_id)
        logger.warning(traceback.format_exc())
    raise


async def get_target_item(target: int, user_id: str = get_user_id()) -> Optional[BagItem]:
    try:
        return await get_bag_item(user_id, target)
    except ItemLockedError:
        await lang.finish(f"move.target_locked", user_id)
        logger.warning(traceback.format_exc())


async def get_count(
    count: int,
    target: Optional[BagItem] = Depends(get_target_item),
    origin: BagItem = Depends(get_origin_item),
    user_id: str = get_user_id(),
) -> int:
    if target is not None:
        count = max(0, min(count, target.stack.getAddableAmount(origin.stack.count)))
    count = max(0, min(origin.stack.count, count))
    if count == 0:
        await lang.finish(f"move.count_error", user_id)
    return count
