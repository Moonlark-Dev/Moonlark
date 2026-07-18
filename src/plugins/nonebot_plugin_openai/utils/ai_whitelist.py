"""
AI 功能白名单工具函数
管理哪些群聊可以使用 AI 功能（仅针对 QQ 官方 Bot）
"""

from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..models import AIWhitelist


def check_ai_enabled() -> bool:
    """检查 AI 功能是否全局启用（运行时检查）"""
    return True


async def is_ai_enabled_for_group(bot: QQBot, group_id: str) -> bool:
    """检查指定 QQ 群是否在 AI 白名单中且已启用"""
    async with get_session() as session:
        result = await session.scalar(select(AIWhitelist).where(AIWhitelist.group_id == group_id))
        return result is not None and result.enabled
