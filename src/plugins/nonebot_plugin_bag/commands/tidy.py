from ..utils.give import give_item_by_list
from ..utils.tidy import get_item_list
from ..item import BagItem
from nonebot.params import Depends
from nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import bag, lang


@bag.assign("tidy")
async def _(item_list: list[BagItem] = Depends(get_item_list), user_id: str = get_user_id()) -> None:
    items = []
    for item in item_list:
        items.append(
            {"item_id": item.stack.item.getLocation().getItemID(), "count": item.stack.count, "data": item.stack.data}
        )
        await item.drop()
    await give_item_by_list(user_id, items)
    await lang.finish("tidy.finish", user_id)
