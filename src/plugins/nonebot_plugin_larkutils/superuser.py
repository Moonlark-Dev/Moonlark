from typing import Any
from nonebot.permission import SuperUser
from nonebot.adapters import Event, Bot
from nonebot.params import Depends

async def _is_superuser(event: Event, bot: Bot) -> bool:
    return await SuperUser()(bot, event)

def is_superuser() -> Any:
    return Depends(_is_superuser)
