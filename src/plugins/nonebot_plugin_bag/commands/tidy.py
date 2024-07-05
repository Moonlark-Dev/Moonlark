from plugins.nonebot_plugin_bag.utils.tidy import get_item_list
from ..item import BagItem
from nonebot.params import Depends
from ...nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import bag, lang


@bag.assign("tidy")
async def _(item_list: list[BagItem] = Depends(get_item_list), user_id: str = get_user_id()) -> None:
    length = 0
    for target in item_list[::-1]:
        length += 1
        for item in item_list[:-length]:
            if item.stack.compare(target.stack) and item.stack.isAddable():
                count = item.stack.getAddableAmount(target.stack.count)
                item.stack.count += count
                target.stack.count -= count
            if target.stack.count <= 0:
                break
    await lang.finish("tidy.finish", user_id)
