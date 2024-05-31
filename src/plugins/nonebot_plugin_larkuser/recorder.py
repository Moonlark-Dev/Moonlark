from datetime import datetime

from nonebot import on_message
from nonebot.matcher import Matcher
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_userinfo import EventUserInfo, UserInfo
from sqlalchemy.exc import NoResultFound

from .model import UserData


@on_message().handle()
async def _(matcher: Matcher, session: async_scoped_session, user: UserInfo = EventUserInfo()) -> None:
    try:
        user_data = await session.get_one(UserData, {"user_id": user.user_id})
    except NoResultFound:
        session.add(
            UserData(
                user_id=user.user_id,
                nickname=user.user_name,
                avatar=(await user.user_avatar.get_image()) if user.user_avatar else None,
                activation_time=datetime.now(),
            )
        )
        await session.commit()
        await matcher.finish()
    if user_data.nickname != user.user_name:
        user_data.nickname = user.user_name
    if user.user_avatar and user_data.avatar != user.user_avatar:
        user_data.avatar = await user.user_avatar.get_image()
    await session.commit()
    await matcher.finish()
