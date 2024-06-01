import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_orm import get_scoped_session, get_session
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from ..nonebot_plugin_larkuser.models import UserData
from ..nonebot_plugin_larkuser.utils.user import get_user
from .models import SessionData


async def create_session(user_id: str, user_agent: str, expiration_time: int) -> tuple[str, str]:
    session_id = str(uuid.uuid4())
    async with get_session() as session:
        session.add(
            SessionData(
                session_id=session_id,
                user_id=user_id,
                user_agent=user_agent,
                expiration_time=datetime.now() + timedelta(days=expiration_time),
                activate_code=(activate_code := str(uuid.uuid4()).split("-")[0]),
            )
        )
        await session.commit()
    return session_id, activate_code


async def _get_user_id(request: Request, session_id: Optional[str] = Cookie(None)) -> Optional[str]:
    logger.debug(f"{session_id=}")
    if session_id is None:
        return None
    session = get_scoped_session()
    try:
        data = await session.get_one(SessionData, session_id)
    except NoResultFound:
        return None
    if (
        data.user_agent != request.headers.get("User-Agent")
        or (datetime.now() - (data.expiration_time or datetime.now())).total_seconds() >= 0
    ):
        await session.delete(data)
    elif data.activate_code is not None:
        pass
    else:
        return data.user_id


def get_user_id() -> Optional[str]:
    return Depends(_get_user_id)


async def _get_user_data(user_id: Optional[str] = get_user_id()) -> Optional[UserData]:
    if user_id is None:
        return None
    return await get_user(user_id)


async def _get_user_forcibly(user_id: Optional[str] = get_user_id()) -> UserData:
    user = await _get_user_data(user_id)
    if user is not None:
        return user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials, please login at /user/login.",
    )


async def _get_user_id_forcibly(user_id: Optional[str] = get_user_id()) -> str:
    if user_id is not None:
        return user_id
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
    )


def get_user_data() -> Optional[UserData]:
    return Depends(_get_user_data)


async def _get_registered_user_data(user_data: UserData = Depends(_get_user_forcibly)) -> UserData:
    if user_data.register_time is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials, please login at /user/login.",
        )
    return user_data


def get_user_forcibly(need_registered: bool = False) -> UserData:
    if not need_registered:
        return Depends(_get_user_forcibly)
    else:
        return Depends(_get_registered_user_data)


def get_user_id_forcibly() -> str:
    return Depends(_get_user_id_forcibly)


@scheduler.scheduled_job("cron", day="*", id="remove_session")
async def _() -> None:
    session = get_session()
    result = await session.scalars(select(SessionData).where(SessionData.expiration_time <= datetime.now()))
    for item in result.all():
        await session.delete(item)
    await session.close()
