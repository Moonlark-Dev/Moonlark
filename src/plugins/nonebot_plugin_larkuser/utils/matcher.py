from typing import Optional

from nonebot.matcher import Matcher
from nonebot_plugin_userinfo import EventUserInfo, UserInfo

from nonebot_plugin_larkutils import get_user_id
from .downed import send_down_prompt
from .register import ensure_registered
from .user import get_user


async def check_access(
    matcher: Matcher = Matcher(),
    user_id: str = get_user_id(),
    user_info: Optional[UserInfo] = EventUserInfo(),
) -> None:
    """检查用户是否可用当前指令。

    - 用户处于倒地状态时发送倒地提示并终止当前响应器；
    - 用户尚未注册时静默完成注册，不再询问昵称或要求确认许可协议。
    """
    user = await get_user(user_id)
    if await user.is_down():
        await send_down_prompt(user_id, user.get_down_remaining())
        await matcher.finish()
    if user.get_register_time() is None:
        await ensure_registered(user_id, user_info)


def patch_matcher(matcher: type[Matcher]) -> type[Matcher]:
    matcher.handle()(check_access)
    matcher.handlers.insert(0, matcher.handlers.pop(-1))
    return matcher
