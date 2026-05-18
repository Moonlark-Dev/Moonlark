import traceback
from typing import Any

from nonebot.adapters import Event
from nonebot.log import logger
from nonebot.params import Depends
from nonebot_plugin_session import SessionId, SessionIdType
from .subaccount import get_main_account


async def _get_user_id(event: Event) -> str:
    try:
        return await get_main_account(event.get_user_id())
    except ValueError:
        logger.error(f"获取用户 ID 失败: {traceback.format_exc()}")
        return "-1"


async def _get_session_user_id(
    session_user_id: str = SessionId(SessionIdType.USER, include_bot_type=False, include_bot_id=False),
) -> str:
    """获取带 platform 前缀的用户 session ID，用于统一 session key 格式"""
    return session_user_id


async def private_message(event: Event) -> bool:
    try:
        return event.get_session_id() == event.get_user_id()
    except ValueError:
        return False


def get_user_id() -> Any:
    return Depends(_get_user_id)


def get_session_user_id() -> Any:
    """返回带 platform 前缀的用户 session ID（如 qq_USERID）"""
    return Depends(_get_session_user_id)


def is_private_message() -> bool:
    return Depends(private_message)
