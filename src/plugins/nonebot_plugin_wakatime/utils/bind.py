from nonebot_plugin_orm import get_session
from typing import Optional

from ...nonebot_plugin_larkutils import get_user_id
from ..__main__ import matcher, lang
from ..utils import get_user_durations
from ..models import User


async def get_wakatime_name(user_id: str) -> Optional[str]:
    async with get_session() as session:
        user = await session.get(User, user_id)
        if user is None:
            return
        return user.user_name
