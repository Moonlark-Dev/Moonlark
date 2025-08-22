from typing import Literal, Union, TypedDict, Awaitable, Callable
from openai.types.responses.response_input_param import Message

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



