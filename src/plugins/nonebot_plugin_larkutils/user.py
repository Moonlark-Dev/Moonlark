import traceback
from typing import Any

from nonebot.adapters import Event
from nonebot.log import logger
from nonebot.params import Depends
from .subaccount import get_main_account


async def _get_user_id(event: Event) -> str:
    try:
        return await get_main_account(event.get_user_id())
    except ValueError:
        logger.error(f"获取用户 ID 失败: {traceback.format_exc()}")
        return "-1"


async def private_message(event: Event) -> bool:
    try:
        return event.get_session_id() == event.get_user_id()
    except ValueError:
        return False


def get_user_id() -> Any:
    return Depends(_get_user_id)


def is_private_message() -> bool:
    return Depends(private_message)
