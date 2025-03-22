from typing import Any
from nonebot.adapters import Bot
from nonebot.adapters.qq.bot import Bot as QQBot
from nonebot.params import Depends


async def _is_public_qq_bot(bot: Bot) -> bool:
    return isinstance(bot, Bot)


def is_public_qq_bot() -> Any:
    return Depends(_is_public_qq_bot)
