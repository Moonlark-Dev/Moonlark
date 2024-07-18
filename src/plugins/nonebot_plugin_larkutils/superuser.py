from typing import Any

from nonebot.adapters import Bot, Event
from nonebot.params import Depends
from nonebot.permission import SuperUser


async def _is_superuser(event: Event, bot: Bot) -> bool:
    return await SuperUser()(bot, event)


def is_user_superuser() -> Any:
    return Depends(_is_superuser)
