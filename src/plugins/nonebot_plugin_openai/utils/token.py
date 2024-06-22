from nonebot_plugin_orm import get_session
from openai.types.chat.chat_completion import ChatCompletion
import random

from ..models import User
from ..config import config


async def is_user_useable(user_id: str) -> bool:
    async with get_session() as session:
        data = await session.get(User, {"user_id": user_id})
        if data is None:
            session.add(User(user_id=user_id))
            await session.commit()
            return True
        return (
            data.plus is not None
            or data.free_count > 0
            or data.tokens > random.randint(*config.openai_min_allowed_token)
        )


def get_used_token(completion: ChatCompletion) -> int:
    if completion.usage is None:
        return 0
    return completion.usage.total_tokens


async def reduce_token(user_id: str, count: int) -> None:
    async with get_session() as session:
        data = await session.get(User, {"user_id": user_id})
        if data is None:
            session.add(User(user_id=user_id, tokens=config.openai_free_token - count))
        elif data.plus is not None:
            return
        elif data.free_count > 0:
            data.free_count -= 1
        else:
            data.tokens -= count
        await session.commit()


async def reduce_completion_token(user_id: str, completion: ChatCompletion, multiple: float = 1.0) -> None:
    return await reduce_token(user_id, round(get_used_token(completion) * multiple))
