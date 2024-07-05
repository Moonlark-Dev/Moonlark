from nonebot_plugin_alconna import UniMessage

from ..utils.show import get_item
from ..utils.show import get_star_string
from ..item import BagItem
from ...nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import bag, lang
from nonebot_plugin_htmlrender import md_to_pic
from nonebot.params import Depends


@bag.assign("show")
async def _(item: BagItem = Depends(get_item), user_id: str = get_user_id()) -> None:
    """展示背包指定物品

    Args:
        item (BagItem, optional): 物品类. Defaults to Depends(get_item).
        user_id (str, optional): 用户ID. Defaults to get_user_id().
    """
    await bag.finish(
        UniMessage().image(
            raw=await md_to_pic(
                await lang.text(
                    "show.info",
                    user_id,
                    await item.stack.getName(),
                    item.stack.count,
                    await get_star_string(item.stack.item.getProperties()["star"], user_id),
                    item.stack.item.getLocation().getItemID(),
                    item.index,
                    await item.stack.getDescription(),
                    item.stack.item.getProperties()["max_stack"],
                    item.stack.item.getProperties()["useable"],
                    item.stack.item.getProperties()["multi_use"],
                )
            )
        ),
        reply_message=True,
    )
