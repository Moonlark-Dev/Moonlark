from nonebot.matcher import Matcher
from nonebot_plugin_orm import get_session
from nonebot_plugin_userinfo import UserInfo, EventUserInfo

from nonebot_plugin_larkutils import get_user_id
from .register import register_user
from ..lang import lang
from .user import get_user


async def check_access(user_id: str = get_user_id(), user_info: UserInfo = EventUserInfo()) -> None:
    if (await get_user(user_id)).register_time is None:
        await lang.send("matcher.not_registered", user_id)
        async with get_session() as session:
            await register_user(session, user_id, user_info)


def patch_matcher(matcher: type[Matcher]) -> type[Matcher]:
    matcher.handle()(check_access)
    matcher.handlers.insert(0, matcher.handlers.pop(-1))
    return matcher
