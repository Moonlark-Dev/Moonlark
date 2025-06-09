from ..utils.session import QuickMathSession
from nonebot_plugin_larkutils.user import get_user_id
from ..__main__ import quick_math


@quick_math.assign("$main")
async def handle(max_level: int = 1, user_id: str = get_user_id()) -> None:
    session = QuickMathSession(user_id)
    session.set_max_level(max_level)
    await session.loop()


@quick_math.assign("max_level")
async def _(max_level: int, user_id: str = get_user_id()) -> None:
    await handle(max_level, user_id)
