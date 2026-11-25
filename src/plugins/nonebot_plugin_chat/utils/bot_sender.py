"""判断群消息的发送者本身是不是机器人。

只有 QQ 官方适配器（以及 Moonlark 使用的 fork）会在群消息事件里给出作者的机器人
标记：群成员作者结构的字段名是 ``bot``，部分版本写作 ``is_bot``，这里两者都兼容。
其余适配器（例如 OneBot V11）的群成员信息里没有可靠的机器人标记，一律视为真人。

机器人账号的消息仍会进入会话上下文（并在 additional_info 中标注），但不会触发
回复；判定发生在消息出队时，因此这里需要的是「事件 + 收消息的 bot」。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nonebot.adapters.qq import Bot as QQBot
from nonebot.adapters.qq.event import GroupMessageCreateEvent

if TYPE_CHECKING:
    from nonebot.adapters import Bot, Event

# 群成员作者结构里机器人标记的候选字段名（fork 与上游不同版本命名不一致）
_BOT_FLAG_FIELDS = ("is_bot", "bot")


def is_bot_sender(event: Event, bot: Bot) -> bool:
    """QQ 官方适配器群消息的发送者是否是机器人。

    ``GroupAtMessageCreateEvent`` 继承自 ``GroupMessageCreateEvent``，同样适用。
    非 QQ 官方适配器、或不是群消息事件时返回 ``False``。
    """
    if not isinstance(bot, QQBot) or not isinstance(event, GroupMessageCreateEvent):
        return False
    author = getattr(event, "author", None)
    for field in _BOT_FLAG_FIELDS:
        value = getattr(author, field, None)
        if isinstance(value, bool):
            return value
    return False
