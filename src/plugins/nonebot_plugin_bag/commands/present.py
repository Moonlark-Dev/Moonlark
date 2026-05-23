from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.params import Depends
from nonebot_plugin_alconna import Alconna, Args, Option, UniMessage, on_alconna
from nonebot_plugin_items.base.gift import GiftItem
from nonebot_plugin_items.exceptions import NotUseableError
from nonebot_plugin_larkuser import patch_matcher
from nonebot_plugin_larkutils.group import get_group_id
from nonebot_plugin_larkutils.user import get_user_id, is_private_message

from ..__main__ import lang
from ..item import BagItem
from ..utils.use import get_item

present = on_alconna(Alconna("present", Args["index", int], Option("--count|-c", Args["count", int, 1])))
patch_matcher(present)


@present.handle()
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
        await lang.finish("present.invalid_count", user_id)
    if count > item.stack.count:
        await item.unlock_item()
        await lang.finish("present.not_enough", user_id, item.stack.count)
    if not isinstance(item.stack.item, GiftItem):
        await item.unlock_item()
        await lang.finish("present.not_gift", user_id)
    if not item.stack.isUseable():
        await item.unlock_item()
        await lang.finish("present.not_useable", user_id)

    before_count = item.stack.count
    try:
        ret = await item.stack.use(
            count=count, bot=bot, event=event, user_id=user_id, group_id=group_id, is_private=is_private
        )
    except NotUseableError:
        await item.unlock_item()
        await lang.finish("present.not_useable", user_id)
    except Exception:
        await item.unlock_item()
        logger.exception("Failed to present bag item")
        await lang.finish("present.failed", user_id)

    item_name = await item.stack.getName()
    if item.stack.count == before_count:
        item.stack.count -= count
    await item.on_delete()
    if isinstance(ret, str) or isinstance(ret, UniMessage):
        await present.finish(ret)
    await lang.finish("present.success", user_id, count, item_name)
