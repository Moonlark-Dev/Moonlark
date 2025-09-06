from typing import Any

from nonebot.adapters import Bot, Event
from nonebot.params import Depends
from nonebot.permission import SuperUser
from .subaccount import get_main_account
from .config import config



async def is_superuser(event: Event, bot: Bot) -> bool:
    try:
        return await get_main_account(event.get_user_id()) in config.superusers
    except ValueError:
        return False


def is_user_superuser() -> Any:
    return Depends(is_superuser)
