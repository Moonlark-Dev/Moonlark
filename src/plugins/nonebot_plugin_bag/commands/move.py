from typing import Literal, Optional
from nonebot.params import Depends
from ..exceptions import ItemLockedError
from ..utils.item import get_bag_item
from ..item import BagItem
from ...nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import bag, lang


async def get_origin_item(origin: int, user_id: str = get_user_id()) -> BagItem:
    try:
        return await get_bag_item(user_id, origin)
    except ItemLockedError:
        await lang.finish(f"move.origin_locked", user_id)
    except IndexError:
        await lang.finish(f"move.origin_index_error", user_id)
    raise


async def get_target_item(target: int, user_id: str = get_user_id()) -> Optional[BagItem]:
    try:
        return await get_bag_item(user_id, target)
    except ItemLockedError:
        await lang.finish(f"move.target_locked", user_id)


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


@bag.assign("move")
async def _(
    target: int,
    target_item: Optional[BagItem] = Depends(get_target_item),
    origin: BagItem = Depends(get_origin_item),
    count: int = Depends(get_count),
    user_id: str = get_user_id(),
) -> None:
    if target_item is not None and target_item.stack.compare(origin.stack):
        target_item.stack.count += count
        origin.stack.count -= count
    elif target_item is not None:
        await lang.finish(f"move.target_item_error", user_id)
    else:
        await origin.set_item_index(target)
    await lang.finish("move.ok", user_id, count, await origin.stack.getName(), target)
