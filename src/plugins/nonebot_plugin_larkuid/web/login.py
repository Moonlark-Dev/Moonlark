import asyncio
import time

from fastapi import HTTPException, Request, status
from nonebot import logger, get_app
from nonebot_plugin_orm import get_session

from ..types import LoginPendingResponse, LoginResponse
from ..models import LoginRequest, SessionData
from ..config import config
from ..session import SessionState, check_session_state, create_session, get_identifier

PENDING_CHECK_INTERVAL = 1


async def remove_unused_session(session_id: str) -> None:
    await asyncio.sleep(config.unused_session_remove_delay)
    async with get_session() as session:
        data = await session.get(SessionData, session_id)
        if data is not None and data.activate_code is not None:
            logger.warning(f"会话 {session_id} 直到过期都未使用，已清理！")
            await session.delete(data)
            await session.commit()


@get_app().post("/api/login")
async def _(request: Request, data: LoginRequest) -> LoginResponse:
    session_id, activate_code = await create_session(data.user_id, get_identifier(request), data.retention_days)
    asyncio.create_task(remove_unused_session(session_id))
    return {
        "session_id": session_id,
        "activate_code": activate_code,
        "effective_time": config.unused_session_remove_delay,
        "command_prefix": config.command_start[0],
    }


@get_app().get("/api/login/pending")
async def _(request: Request, wait: int = 0) -> LoginPendingResponse:
    """查询当前会话是否已完成登录激活。

    `wait`（秒）大于 0 时为长轮询：服务端挂起请求，激活后立即返回，
    或到达超时上限（`login_pending_max_wait`，最长不超过该值）返回 `{"activated": false}`。
    前端只需每 ~25s 发起一次请求即可获得毫秒级的激活感知，替代原先的每秒轮询。
    会话无效 / 已过期时返回 401。
    """
    deadline = time.monotonic() + min(max(wait, 0), config.login_pending_max_wait)
    while True:
        state = await check_session_state(request)
        if state == SessionState.INVALID:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        if state == SessionState.ACTIVATED or time.monotonic() >= deadline:
            return {"activated": state == SessionState.ACTIVATED}
        await asyncio.sleep(PENDING_CHECK_INTERVAL)
