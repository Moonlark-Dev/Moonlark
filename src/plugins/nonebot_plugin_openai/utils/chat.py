from typing import Literal

from nonebot import logger

from ..types import Messages

from ..config import config
from .message import generate_message
from .client import get_completion, get_reply


async def fetch_messages(
    messages: Messages,
    use_default_message: bool = False,
    model: str = config.openai_default_model,
    **kwargs,
) -> str:
    if use_default_message:
        messages.insert(0, generate_message(config.openai_default_message, "system"))
    completion = await get_completion(messages, model, **kwargs)
    logger.debug(reply := get_reply(completion))
    return reply


async def fetch(
    prompt: str,
    role: Literal["system", "user"] = "user",
    use_default_message: bool = False,
    model: str = config.openai_default_model,
    **kwargs,
) -> str:
    messages = [generate_message(prompt, role)]
    return await fetch_messages(messages, use_default_message, model, **kwargs)
