from ...nonebot_plugin_bag.exceptions import ItemLockedError
from ...nonebot_plugin_bag.utils.item import get_bag_item
from ...nonebot_plugin_bag.item import BagItem
from ..lang import lang
from nonebot.log import logger


async def get_target_item(index: int, count: int, user_id: str) -> BagItem:
    try:
        target_item = await get_bag_item(user_id, index)
    except IndexError:
        logger.waring(f"{traceback.format_exc()}")
        await lang.finish("bag_error.not_found", user_id)
    except ItemLockedError:
        logger.waring(f"{traceback.format_exc()}")
        await lang.finish("bag_error.locked", user_id)
    if target_item.stack.count < count:
        await lang.finish("pcc.not_enough_item", user_id, target_item.stack.count)
    return target_item
