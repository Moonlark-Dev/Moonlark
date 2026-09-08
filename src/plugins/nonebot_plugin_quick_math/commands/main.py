from typing import Optional

from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Match

from ..utils.session import QuickMathSession, QuickMathZenSession
from nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import quick_math


def get_qq_user_id(bot: Bot, event: Event) -> Optional[str]:
    """获取 QQ 官方机器人事件中的用户 ID（用于 markdown 卡片内 @ 用户）。"""
    if isinstance(bot, QQBot):
        return event.get_user_id()
    return None


@quick_math.assign("start")
async def start_handler(bot: Bot, event: Event, max_level: Match[int], user_id: str = get_user_id()) -> None:
    session = QuickMathSession(user_id, bot, get_qq_user_id(bot, event), event)
    if max_level.available:
        session.set_max_level(max_level.result)
    await session.loop()


@quick_math.assign("zen")
async def zen_handler(bot: Bot, event: Event, zen_level: int, user_id: str = get_user_id()) -> None:
    session = QuickMathZenSession(user_id, zen_level, bot, get_qq_user_id(bot, event), event)
    await session.loop()
