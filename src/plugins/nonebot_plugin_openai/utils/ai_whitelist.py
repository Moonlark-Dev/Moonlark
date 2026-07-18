"""
AI 功能白名单工具函数
提供 Depends 注入式 AI 功能开关检测
"""

from typing import Any

from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as Bot_QQ
from nonebot.params import Depends
from nonebot_plugin_larkutils import get_group_id as _get_group_id
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..models import AIWhitelist


async def is_ai_enabled_for_group(bot: Bot, group_id: str) -> bool:
    """检查指定群聊是否在 AI 白名单中且已启用"""
    async with get_session() as session:
        result = await session.scalar(
            select(AIWhitelist.enabled).where(AIWhitelist.group_id == group_id)
        )
        if result:
            return True
    return not isinstance(bot, Bot_QQ)


async def _check_ai_enabled(bot: Bot, group_id: str = _get_group_id()) -> bool:
    return await is_ai_enabled_for_group(bot, group_id)


def check_ai_enabled() -> Any:
    """Depends 注入式依赖，检查当前群聊的 AI 功能是否启用

    Default Rules (priority order):
    1. Group in whitelist (AIWhitelist table) -> enabled
    2. QQ Bot (official adapter) -> disabled
    3. All others -> enabled
    """
    return Depends(_check_ai_enabled)
