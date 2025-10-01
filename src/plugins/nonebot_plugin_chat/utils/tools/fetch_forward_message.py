
from typing import Any, Awaitable, Callable
from nonebot.adapters.onebot.v11 import Bot as OB11Bot
from nonebot.adapters import Bot


def get_fetcher(bot: Bot) -> Callable[[str], Awaitable[dict[str, Any]]]:
    async def fetch_forward_message(forward_id: str) -> dict[str, Any]:
        if isinstance(bot, OB11Bot):
            return await bot.get_forward_msg(id=forward_id)
        return {"state": "failed", "message": "not supported"}
    return fetch_forward_message
