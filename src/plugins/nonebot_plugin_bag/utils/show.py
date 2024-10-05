from ...nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import lang
from ..item import BagItem
from .item import get_bag_item
from nonebot.log import logger


async def get_item(index: int, user_id: str = get_user_id()) -> BagItem:
    """获取用户想要展示的物品（请使用依赖注入）"""
    try:
        item = await get_bag_item(user_id, index, True)
    except IndexError:
        await lang.finish("show.index_error", user_id, reply_message=True, at_sender=False)
        logger.warning(traceback.format_exc())
    return item


async def get_star_string(star: int, user_id: str) -> str:
    return (await lang.text("show.star", user_id)) * star
