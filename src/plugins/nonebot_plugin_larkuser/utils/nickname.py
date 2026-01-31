from nonebot.adapters import Bot, Event
from .user import get_user
from nonebot_plugin_userinfo import get_user_info


async def get_nickname(user_id: str, bot: Bot, event: Event) -> str:
    user_info = await get_user_info(bot, event, user_id)
    user = await get_user(user_id)
    if user.has_nickname() or not user_info:
        nickname = user.get_nickname()
    else:
        nickname = user_info.user_displayname or user_info.user_name
    return nickname
