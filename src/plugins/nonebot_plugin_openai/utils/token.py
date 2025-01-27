from nonebot_plugin_orm import get_session
from openai.types.chat.chat_completion import ChatCompletion
from nonebot_plugin_larkuser import get_user
import random

from ..models import GptUser
from ..config import config


async def is_user_useable(user_id: str) -> bool:
    return (await get_user(user_id)).is_registered()


def get_used_token(completion: ChatCompletion) -> int:
    if completion.usage is None:
        return 0
    return completion.usage.total_tokens


async def reduce_token(user_id: str, count: int) -> None:
    async with get_session() as session:
        if (user := await session.get(GptUser, user_id)) is not None:
            user.used_token += count
        else:
            user = GptUser(user_id=user_id, used_token=count)
        await session.merge(user)
        await session.commit()


async def reduce_completion_token(user_id: str, completion: ChatCompletion, multiple: float = 1.0) -> None:
    return await reduce_token(user_id, round(get_used_token(completion) * multiple))
