from typing import Any

from openai import AsyncOpenAI
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_message import ChatCompletionMessage

from ..exceptions import EmptyReplyContent
from ..config import config
from ..types import Messages

client = AsyncOpenAI(api_key=config.openai_api_key, base_url=config.openai_base_url)

