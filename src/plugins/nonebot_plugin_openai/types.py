from typing import TypedDict, Awaitable, Callable
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolMessageParam, ChatCompletionMessage, ChatCompletionTool

Message = ChatCompletionMessageParam | ChatCompletionToolMessageParam | ChatCompletionMessage | ChatCompletionTool
Messages = list[Message]

class FunctionParameter(TypedDict):
    type: str
    description: str
    required: bool

class FunctionParameterWithEnum(FunctionParameter):
    enum: set


class AsyncFunction(TypedDict):
    func: Callable[[...], Awaitable[str]]
    description: str
    parameters: dict[str, FunctionParameter | FunctionParameterWithEnum]



