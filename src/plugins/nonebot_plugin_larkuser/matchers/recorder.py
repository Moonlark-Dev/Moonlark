from ..utils.avatar import is_user_avatar_updated, update_user_avatar
from ..utils.user import get_user
from nonebot_plugin_larkutils import get_main_account
from nonebot import on_message
from nonebot.log import logger
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_userinfo import EventUserInfo, UserInfo
from sqlalchemy.exc import NoResultFound
import json
import base64
from ..models import UserData


async def checker(user: UserInfo = EventUserInfo()) -> bool:
    u = await get_user(user.user_id)
    return u.is_main_account() and not u.get_config_key("lock_nickname_and_avatar", False)


@on_message(block=False, priority=5, rule=checker).handle()
async def _(session: async_scoped_session, user: UserInfo = EventUserInfo()) -> None:
    try:
        user_data = await session.get_one(UserData, {"user_id": user.user_id})
    except NoResultFound:
        return
    config = json.loads(base64.b64decode(user_data.config))
    if user_data.nickname != user.user_name and not config.get("lock_nickname"):
        logger.info(f"用户 {user_data.user_id} 修改了其昵称 ({user_data.nickname} => {user.user_name})")
        user_data.nickname = user.user_name
    if user.user_avatar and user_data.register_time and not config.get("lock_avatar"):
        avatar = await user.user_avatar.get_image()
        if await is_user_avatar_updated(user_data.user_id, avatar):
            await update_user_avatar(user_data.user_id, avatar)
            logger.info(f"注册用户 {user_data.user_id} 更新了其头像")
    await session.commit()
