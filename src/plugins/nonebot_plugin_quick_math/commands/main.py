from typing import Optional

from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot.adapters.qq.event import C2CMessageCreateEvent

from ..utils.session import QuickMathSession, QuickMathZenSession
from nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import quick_math


def get_qq_user_id(bot: Bot, event: Event) -> Optional[str]:
    """获取 QQ 官方机器人事件中的用户 ID（用于 markdown 卡片内 @ 用户）。

    C2C 单聊消息不支持 ``<qqbot-at-user>`` 提及语法（发送会报 ActionFailed），
    因此返回 ``None`` 跳过 @ 前缀；单聊中无需 @ 用户。
    """
    if isinstance(bot, QQBot) and not isinstance(event, C2CMessageCreateEvent):
        return event.get_user_id()
    return None


@quick_math.assign("max_level")
async def max_level_handler(bot: Bot, event: Event, max_level: int, user_id: str = get_user_id()) -> None:
    await handle(bot, event, max_level, user_id)


@quick_math.assign("zen")
async def zen_handler(bot: Bot, event: Event, zen_level: int, user_id: str = get_user_id()) -> None:
    session = QuickMathZenSession(user_id, zen_level, bot, get_qq_user_id(bot, event), event)
    await session.loop()


@quick_math.assign("$main")
async def handle(bot: Bot, event: Event, max_level: int = 1, user_id: str = get_user_id()) -> None:
    session = QuickMathSession(user_id, bot, get_qq_user_id(bot, event), event)
    session.set_max_level(max_level)
    await session.loop()
