from nonebot.matcher import Matcher

from ..nonebot_plugin_larkutils.user import get_user_id
from .lang import lang
from .utils.user import get_user


async def check_access(user_id: str = get_user_id()) -> None:
    if (await get_user(user_id)).register_time is None:
        await lang.finish("matcher.not_registered", user_id)


def patch_matcher(matcher: type[Matcher]) -> type[Matcher]:
    matcher.handle()(check_access)
    matcher.handlers.insert(0, matcher.handlers.pop(-1))
    return matcher
