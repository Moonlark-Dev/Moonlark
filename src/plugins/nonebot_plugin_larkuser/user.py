import datetime
from typing import Optional
from .model import UserData
from nonebot_plugin_orm import AsyncSession, async_scoped_session, get_session
from sqlalchemy.exc import NoResultFound


async def get_user(user_id: str, s: Optional[async_scoped_session | AsyncSession] = None) -> UserData:
    session = s or get_session()
    try:
        return await session.get_one(
            UserData,
            {'user_id': user_id}
        )
    except NoResultFound:
        data = UserData(
            user_id=user_id,
            nickname="",
            activation_time=datetime.datetime.now()
        )
        session.add(data)
        await session.commit()
    return await get_user(user_id)

async def set_user_data(
        user_id: str,
        experience: Optional[int] = None,
        vimcoin: Optional[float] = None,
        health: Optional[float] = None,
        favorability: Optional[float] = None
) -> None:
    session = get_session()
    user = await get_user(user_id)
    if experience:
        user.experience = experience
    if vimcoin:
        user.vimcoin = vimcoin
    if health:
        user.health = health
    if favorability:
        user.favorability = favorability
    await session.commit()