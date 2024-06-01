from datetime import datetime, timedelta

from nonebot_plugin_orm import async_scoped_session
from sqlalchemy.exc import NoResultFound

from .config import config
from .model import GroupData, UserCoolDownData


async def is_group_cooled(group_id: str, session: async_scoped_session) -> tuple[bool, float]:
    try:
        data = await session.get_one(GroupData, {"group_id": group_id})
    except NoResultFound:
        return True, 0
    remain = (timedelta(minutes=data.cool_down_time) - (datetime.now() - data.last_use)).total_seconds()
    return remain <= 0, remain


async def on_group_use(group_id: str, session: async_scoped_session) -> None:
    try:
        data = await session.get_one(GroupData, {"group_id": group_id})
    except NoResultFound:
        session.add(GroupData(group_id=group_id, last_use=datetime.now()))
    else:
        data.last_use = datetime.now()
    await session.commit()


async def is_user_cooled(user_id: str, session: async_scoped_session) -> tuple[bool, float]:
    try:
        data = await session.get_one(UserCoolDownData, {"user_id": user_id})
    except NoResultFound:
        return True, 0
    remain = (timedelta(minutes=config.cave_user_cd) - (datetime.now() - data.last_use)).total_seconds()
    return remain <= 0, remain


async def on_user_use(user_id: str, session: async_scoped_session) -> None:
    try:
        data = await session.get_one(UserCoolDownData, {"user_id": user_id})
    except NoResultFound:
        session.add(UserCoolDownData(user_id=user_id, last_use=datetime.now()))
    else:
        data.last_use = datetime.now()
    await session.commit()


async def on_use(group_id: str, user_id: str, session: async_scoped_session) -> None:
    await on_group_use(group_id, session)
    await on_user_use(user_id, session)
