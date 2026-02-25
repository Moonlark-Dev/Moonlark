from typing import Any

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import UniMessage

from ..utils.use import get_item
from nonebot_plugin_larkutils.user import get_user_id
from ..item import BagItem
from ..__main__ import bag, lang
from nonebot.params import Depends


@bag.assign("use")
async def _(
    bot: Bot,
    event: Event,
    args: list[Any],
    count: int,
    item: BagItem = Depends(get_item),
    user_id: str = get_user_id(),
) -> None:
    if 0 < count < item.stack.count:
        await lang.finish("use.not_enough", user_id, item.stack.count)
    elif item.stack.item.getProperties()["multi_use"] and count != 1:
        await lang.finish("use.unsupported_count", user_id)
    elif not item.stack.isUseable():
        await lang.finish("use.not_useable", user_id)

    # 传递上下文信息给物品使用，由 GiftItem 判断 session 类型
    ret = await item.stack.use(*args, count=count, bot=bot, event=event, user_id=user_id)
    if isinstance(ret, str) or isinstance(ret, UniMessage):
        await bag.finish(ret)
