from typing import Any

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import UniMessage

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
    args: list[Any],
    count: int,
    item: BagItem = Depends(get_item),
    user_id: str = get_user_id(),
    is_private: bool = is_private_message(),
    group_id: str = get_group_id(),
) -> None:
    if 0 < count < item.stack.count:
        await lang.finish("use.not_enough", user_id, item.stack.count)
    elif item.stack.item.getProperties()["multi_use"] and count != 1:
        await lang.finish("use.unsupported_count", user_id)
    elif not item.stack.isUseable():
        await lang.finish("use.not_useable", user_id)
    
    # 根据场景确定 session_id：私聊用 user_id，群聊用 group_id
    session_id = user_id if is_private else group_id
    
    # 传递上下文信息给物品使用
    ret = await item.stack.use(
        *args, count=count, bot=bot, event=event, user_id=user_id, session_id=session_id, is_private=is_private
    )
    if isinstance(ret, str) or isinstance(ret, UniMessage):
        await bag.finish(ret)
