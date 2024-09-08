from ..utils.avatar import is_user_avatar_updated, update_user_avatar
from ...nonebot_plugin_larkutils import get_main_account
from nonebot import on_message
from nonebot.log import logger
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_userinfo import EventUserInfo, UserInfo
from sqlalchemy.exc import NoResultFound

from ..models import UserData


@on_message(block=False, priority=5).handle()
async def _(session: async_scoped_session, user: UserInfo = EventUserInfo()) -> None:
    if user.user_id != await get_main_account(user.user_id):
        return
    try:
        user_data = await session.get_one(UserData, {"user_id": user.user_id})
    except NoResultFound:
        logger.info(f"识别到新用户 {user.user_id=}")
        user_data = UserData(user_id=user.user_id, nickname=user.user_name)
        session.add(user_data)
        return await session.commit()
    if user_data.nickname != user.user_name:
        logger.info(f"用户 {user_data.user_id} 修改了其昵称 ({user_data.nickname} => {user.user_name})")
        user_data.nickname = user.user_name
    logger.debug(f"{user_data.register_time=} {user.user_avatar=}")
    if user.user_avatar and user_data.register_time:
        avatar = await user.user_avatar.get_image()
        if await is_user_avatar_updated(user_data.user_id, avatar):
            await update_user_avatar(user_data.user_id, avatar)
            logger.info(f"注册用户 {user_data.user_id} 更新了其头像")
    await session.commit()
