import uuid
import hashlib
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_orm import get_session
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkuser.user.base import MoonlarkUser
from .models import SessionData


class SessionState(Enum):
    """Web 会话状态：已激活、待激活、无效（不存在 / 已过期 / 标识不匹配）。"""

    ACTIVATED = "activated"
    PENDING = "pending"
    INVALID = "invalid"


def get_identifier(request: Request) -> str:
    return hashlib.sha256(
        f"{request.headers.get('User-Agent')}{request.client.host if request.client else ''}".encode()
    ).hexdigest()


async def check_session_state(request: Request) -> SessionState:
    """按 Bearer Token 检查会话状态（主键查询，开销极小，供登录等待轮询使用）。

    与 `_get_user_id` 不同：待激活的会话返回 PENDING 而不是 401；
    无效 / 过期 / 标识不匹配的会话会被删除并返回 INVALID。
    """
    session_id = (request.headers.get("Authorization") or "")[6:].strip()
    if not session_id:
        return SessionState.INVALID
    async with get_session() as session:
        try:
            data = await session.get_one(SessionData, session_id)
        except NoResultFound:
            return SessionState.INVALID
        expired = data.expiration_time is not None and data.expiration_time <= datetime.now()
        if data.identifier != get_identifier(request) or expired:
            await session.delete(data)
            await session.commit()
            return SessionState.INVALID
        return SessionState.ACTIVATED if data.activate_code is None else SessionState.PENDING


async def create_session(user_id: str, identifier: str, expiration_time: int) -> tuple[str, str]:
    session_id = uuid.uuid4().hex
    async with get_session() as session:
        session.add(
            SessionData(
                session_id=session_id,
                user_id=user_id,
                identifier=identifier,
                expiration_time=datetime.now() + timedelta(days=expiration_time),
                activate_code=(activate_code := str(uuid.uuid4()).split("-")[0]),
            )
        )
        await session.commit()
    return session_id, activate_code


async def _get_user_id(request: Request) -> str:
    session_id = (request.headers.get("Authorization") or "")[6:].strip()
    logger.debug(f"{session_id=}")
    if session_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    session = get_session()
    try:
        data = await session.get_one(SessionData, session_id)
    except NoResultFound:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    user_id = data.user_id
    tomorrow = datetime.now() + timedelta(days=1)
    logger.debug(f"{user_id=}")
    if (
        data.identifier != get_identifier(request)
        or (datetime.now() - (data.expiration_time or tomorrow)).total_seconds() > 0
    ):
        await session.delete(data)
        await session.commit()
    elif data.activate_code is None:
        await session.close()
        return user_id
    await session.close()
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


def get_user_id(default: Optional[str] = None) -> str:
    if default is None:
        return Depends(_get_user_id)
    else:

        async def _(request: Request) -> str:
            try:
                return await _get_user_id(request)
            except HTTPException:
                return default

        return Depends(_)


async def _get_existing_user(user_id: str = get_user_id()) -> MoonlarkUser:
    try:
        return await get_user(user_id)
    except NoResultFound:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


async def _get_user_data(user_id: str = get_user_id()) -> MoonlarkUser:
    return await get_user(user_id)


async def _get_registered_user(user_data: MoonlarkUser = Depends(_get_existing_user)) -> MoonlarkUser:
    if not user_data.is_registered():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return user_data


def get_user_data(registered: bool = False) -> MoonlarkUser:
    if registered:
        return Depends(_get_registered_user)
    return Depends(_get_user_data)


@scheduler.scheduled_job("cron", day="*", id="remove_session")
async def _() -> None:
    session = get_session()
    result = await session.scalars(select(SessionData).where(SessionData.expiration_time <= datetime.now()))
    for item in result.all():
        await session.delete(item)
    await session.commit()
    await session.close()
