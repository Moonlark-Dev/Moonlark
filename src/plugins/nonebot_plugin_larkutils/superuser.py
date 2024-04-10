from nonebot.permission import SuperUser
from nonebot.adapters import Event, Bot
from nonebot.params import Depends

async def _is_superuser(event: Event, bot: Bot) -> bool:
    return await SuperUser()(bot, event)
is_superuser = Depends(_is_superuser)
