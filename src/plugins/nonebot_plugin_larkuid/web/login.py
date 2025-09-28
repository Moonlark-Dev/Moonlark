import asyncio
from fastapi import Request
from nonebot import logger, get_app
from nonebot_plugin_orm import get_session

# import nonebot_plugin_larkcave.comment.__main__
# import nonebot_plugin_larkcave.utils.comment.post
from ..types import LoginResponse
from ..models import LoginRequest, SessionData
from ..config import config
from ..session import create_session, get_identifier


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
    }
