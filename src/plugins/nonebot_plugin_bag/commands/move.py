from typing import Optional
from nonebot.params import Depends

from ..utils.move import get_origin_item
from ..utils.move import get_target_item
from ..utils.move import get_count
from ..item import BagItem
from nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import bag, lang


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
