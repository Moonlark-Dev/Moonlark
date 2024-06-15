from typing import Literal

from nonebot import logger

from ..types import Messages

from ..config import config
from ..exceptions import NoTokenException
from .token import is_user_useable, reduce_completion_token
from .message import generate_message
from .client import get_completion, get_reply


async def fetch_messages(
    messages: Messages,
    user_id: str,
    use_default_message: bool = False,
    multiple: float = 0.0,
    model: str = config.openai_default_model,
    **kwargs,
) -> str:
    logger.debug(messages)
    if multiple != 0 and not await is_user_useable(user_id):
        raise NoTokenException()
    if use_default_message:
        messages.insert(0, generate_message(config.openai_default_message, "system"))
    completion = await get_completion(messages, model, **kwargs)
    await reduce_completion_token(user_id, completion, multiple)
    logger.debug(reply := get_reply(completion))
    return reply


async def fetch(
    prompt: str,
    user_id: str,
    role: Literal["system", "user"] = "user",
    use_default_message: bool = False,
    multiple: float = 0.0,
    model: str = config.openai_default_model,
    **kwargs,
) -> str:
    messages = [generate_message(prompt, role)]
    return await fetch_messages(messages, user_id, use_default_message, multiple, model, **kwargs)
