from datetime import datetime, timedelta
from nonebot_plugin_alconna import UniMessage

from ...utils.overflow import get_overflow_item
from ...config import config
from ...utils.show import get_star_string
from ...item import BagItem
from ....nonebot_plugin_larkutils.user import get_user_id
from ...__main__ import bag, lang
from nonebot_plugin_htmlrender import md_to_pic
from nonebot.params import Depends
from nonebot.log import logger

@bag.assign("overflow.show")
async def _(index: int, user_id: str = get_user_id()) -> None:
    try:
        item_data = await get_overflow_item(index)
    except IndexError:
        await lang.finish("overflow_show.not_found", user_id)
        logger.warning(f"User {user_id}'s overflow show isn't found.  {traceback.format_exc()}")
    item = item_data["item"]
    await bag.finish(
        UniMessage().image(
            raw=await md_to_pic(
                await lang.text(
                    ".info",
                    user_id,
                    await item.getName(),
                    item.count,
                    await get_star_string(item.item.getProperties()["star"], user_id),
                    item.item.getLocation().getItemID(),
                    item_data["index"],
                    await item.getDescription(),
                    item.user_id,
                    datetime.now() <= item_data["time"] + timedelta(hours=config.overflow_protect_hours),
                    (item_data["time"] + timedelta(hours=config.overflow_protect_hours)).strftime("%Y-%m-%d %H:%M:%S"),
                    item.item.getProperties()["max_stack"],
                    item.item.getProperties()["useable"],
                    item.item.getProperties()["multi_use"],
                )
            )
        ),
        reply_message=True,
    )
