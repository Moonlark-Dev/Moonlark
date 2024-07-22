from nonebot_plugin_orm import get_session

from ...nonebot_plugin_larkutils import get_user_id
from ..__main__ import matcher, lang
from ..utils import get_user_durations
from ..models import User


@matcher.assign("bind")
async def _(user_name: str, user_id: str = get_user_id()) -> None:
    if not await get_user_durations(user_name):
        await lang.finish("bind.failed", user_id, user_name)
    async with get_session() as session:
        user = User(user_id=user_id, user_name=user_name)
        await session.merge(user)
        await session.commit()
    await lang.finish("bind.success", user_id, user_name)
