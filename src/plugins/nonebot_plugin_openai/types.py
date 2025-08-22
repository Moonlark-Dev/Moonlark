from typing import TypedDict, Awaitable, Callable, Any
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolMessageParam, ChatCompletionMessage

Message = ChatCompletionMessageParam | ChatCompletionToolMessageParam | ChatCompletionMessage
Messages = list[Message]

class FunctionParameter(TypedDict):
    type: str
    description: str
    required: bool

class FunctionParameterWithEnum(FunctionParameter):
    enum: set


class AsyncFunction(TypedDict):
    func: Callable[[...], Awaitable[Any]]
    description: str
    parameters: dict[str, FunctionParameter | FunctionParameterWithEnum]



