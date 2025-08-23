from typing import Any

from openai import AsyncOpenAI
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_message import ChatCompletionMessage

from ..exceptions import EmptyReplyContent
from ..config import config
from ..types import Messages

client = AsyncOpenAI(api_key=config.openai_api_key, base_url=config.openai_base_url)


async def get_completion(
    messages: Messages, functions: list[dict[str, Any]], model: str = config.openai_default_model, **kwargs
) -> ChatCompletion:
    return await client.chat.completions.create(messages=messages, model=model, **kwargs)


def get_reply_message(completion: ChatCompletion) -> ChatCompletionMessage:
    return completion.choices[0].message


def get_reply_content(message: ChatCompletionMessage) -> str:
    if message.content is None:
        raise EmptyReplyContent()
    return message.content


def get_reply(completion: ChatCompletion) -> str:
    return get_reply_content(get_reply_message(completion))
