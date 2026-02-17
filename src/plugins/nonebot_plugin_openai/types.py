from typing import Literal, TypedDict, Awaitable, Callable, Any
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolMessageParam, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

Message = ChatCompletionMessageParam | ChatCompletionToolMessageParam | ChatCompletionMessage
Messages = list[Message]


class FunctionParameter(TypedDict):
    type: str
    description: str
    required: bool


class FunctionParameterWithEnum(FunctionParameter):
    enum: set


class AsyncFunction(TypedDict):
    func: Callable[..., Awaitable[Any]]
    description: str
    parameters: dict[str, FunctionParameter | FunctionParameterWithEnum]


class StopSessionStrategy(TypedDict):
    strategy: Literal["throw"]


class ReplaceResponseStrategy(TypedDict):
    strategy: Literal["replace"]
    choice: Choice


TimeoutStrategy = ReplaceResponseStrategy | StopSessionStrategy
