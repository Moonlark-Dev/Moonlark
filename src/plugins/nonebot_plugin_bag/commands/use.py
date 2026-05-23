from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_items.base.gift import GiftItem
from nonebot_plugin_items.exceptions import NotUseableError

from ..utils.use import get_item
from nonebot_plugin_larkutils.user import get_user_id, is_private_message
from nonebot_plugin_larkutils.group import get_group_id
from ..item import BagItem
from ..__main__ import bag, lang
from nonebot.params import Depends


@bag.assign("use")
async def _(
    bot: Bot,
    event: Event,
    count: int,
    item: BagItem = Depends(get_item),
    user_id: str = get_user_id(),
    is_private: bool = is_private_message(),
    group_id: str = get_group_id(),
) -> None:
    if count <= 0:
        await item.unlock_item()
        await lang.finish("use.invalid_count", user_id)
    if count > item.stack.count:
        await item.unlock_item()
        await lang.finish("use.not_enough", user_id, item.stack.count)
    if isinstance(item.stack.item, GiftItem):
        await item.unlock_item()
        await lang.finish("use.gift_deprecated", user_id)
    if not item.stack.item.getProperties()["multi_use"] and count != 1:
        await item.unlock_item()
        await lang.finish("use.unsupported_count", user_id)
    if not item.stack.isUseable():
        await item.unlock_item()
        await lang.finish("use.not_useable", user_id)

    try:
        ret = await item.stack.use(
            count=count, bot=bot, event=event, user_id=user_id, group_id=group_id, is_private=is_private
        )
    except NotUseableError:
        await item.unlock_item()
        await lang.finish("use.not_useable", user_id)
    except Exception:
        await item.unlock_item()
        logger.exception("Failed to use bag item")
        await lang.finish("use.failed", user_id)

    await item.on_delete()
    if isinstance(ret, str) or isinstance(ret, UniMessage):
        await bag.finish(ret)
    await lang.finish("use.success", user_id)
