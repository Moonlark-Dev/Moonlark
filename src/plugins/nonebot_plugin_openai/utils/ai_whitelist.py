from typing import Any

from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as Bot_QQ
from nonebot.params import Depends
from nonebot_plugin_larkutils import get_group_id as _get_group_id
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..models import AIWhitelist


async def is_ai_enabled_for_group(bot: Bot, group_id: str) -> bool:
    async with get_session() as session:
        result = await session.scalar(select(AIWhitelist.enabled).where(AIWhitelist.group_id == group_id))
        if result:
            return True
    return not isinstance(bot, Bot_QQ)


async def _check_ai_enabled(bot: Bot, group_id: str = _get_group_id()) -> bool:
    return await is_ai_enabled_for_group(bot, group_id)


def check_ai_enabled() -> Any:
    return Depends(_check_ai_enabled)
