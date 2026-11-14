from typing import Awaitable, Callable, Literal, Optional, Any
from typing_extensions import TypedDict

from google.genai.types import GenerateContentResponse
from pydantic import BaseModel

# 消息一律沿用 OpenAI 风格的 dict（与 nonebot_plugin_openai.types.Messages 兼容），
# 发请求前由 utils/convert.py 统一转换成 Gemini 的 Content 列表。
# 这样 Chat 等调用方在两套 SDK 之间切换时不需要修改消息结构。
Message = dict[str, Any]
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
    choice: GenerateContentResponse


TimeoutStrategy = ReplaceResponseStrategy | StopSessionStrategy


class FunctionParameterDefinition(BaseModel):
    type: str
    description: str
    required: bool = True
    enum: Optional[list[str]] = None
    name: str


class MoonlarkFunctionDefinition(BaseModel):
    description: str
    parameters: list[FunctionParameterDefinition]
