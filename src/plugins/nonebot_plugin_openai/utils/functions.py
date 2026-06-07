from nonebot.compat import type_validate_json, type_validate_python
from collections.abc import Awaitable

from nonebot_plugin_openai.types import AsyncFunction, FunctionParameter, FunctionParameterWithEnum, MoonlarkFunctionDefinition
from openai.types.chat import ChatCompletionFunctionToolParam
from openai.types.shared_params import FunctionDefinition


from typing import Any, Callable


def generate_function_list(func_index: dict[str, AsyncFunction]) -> list[ChatCompletionFunctionToolParam]:
    func_list = []
    for name, data in func_index.items():
        func_info = FunctionDefinition(
            name=name,
            description=data["description"],
            parameters={"type": "object", "properties": {}, "required": []},
            strict=True,
        )
        for p_name, p_data in data["parameters"].items():
            param_info: dict[str, Any] = {"type": p_data["type"], "description": p_data["description"]}
            if "enum" in p_data:
                param_info["enum"] = list(p_data["enum"])
            func_info["parameters"]["properties"][p_name] = param_info  # type: ignore
            if p_data["required"]:
                func_info["parameters"]["required"].append(p_name)  # type: ignore
        func_list.append(
            ChatCompletionFunctionToolParam(
                type="function",
                function=func_info,
            )
        )
    return func_list

import aiofiles
import yaml

async def create_function_list(functions: list[Callable[..., Awaitable[Any]]], **kwargs) -> list[AsyncFunction]:
    func_list = []
    for func in functions:
        name = func.__name__
        async with aiofiles.open(f"./src/prompt/__tools__/{name}.yaml", "r", encoding="utf-8") as f:
            func_info = type_validate_python(MoonlarkFunctionDefinition, yaml.parse(await f.read()))
        parameters = {}
        for param in func_info.parameters:
            if param.enum:
                parameters[param.name] = FunctionParameterWithEnum(
                    type=param.type,
                    description=param.description,
                    required=param.required,
                    enum=set(param.enum),
                )
            else:
                parameters[param.name] = FunctionParameter(
                    type=param.type,
                    description=param.description,
                    required=param.required,
                )
        func_list.append(AsyncFunction(
            func=func,
            description=func_info.description,
            parameters=parameters,
        ))
    return func_list