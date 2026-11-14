"""工具列表生成

``create_function_list`` 从 ``src/prompt/__tools__/<函数名>.yaml`` 读取工具描述，
``generate_function_list`` 把的工具表转换成 Gemini SDK 的 ``Tool``。
参数直接以 JSON Schema 交给 SDK（``parameters_json_schema``），避免再经过一层
``types.Schema`` 转换——Moonlark 的工具参数只用到 string / integer / number /
boolean 与 enum，都在 Gemini 支持的 JSON Schema 子集内。
"""

from collections.abc import Awaitable
from typing import Any, Callable

import aiofiles
import yaml
from google.genai import types
from nonebot.compat import type_validate_python

from ..types import (
    AsyncFunction,
    FunctionParameter,
    FunctionParameterWithEnum,
    MoonlarkFunctionDefinition,
)


def generate_function_list(func_index: dict[str, AsyncFunction]) -> list[types.Tool]:
    """把工具表转换成 Gemini SDK 的 Tool 列表（没有工具时返回空列表）"""
    declarations = []
    for name, data in func_index.items():
        properties: dict[str, Any] = {}
        required: list[str] = []
        for p_name, p_data in data["parameters"].items():
            param_info: dict[str, Any] = {"type": p_data["type"], "description": p_data["description"]}
            if "enum" in p_data:
                param_info["enum"] = list(p_data["enum"])
            properties[p_name] = param_info
            if p_data["required"]:
                required.append(p_name)
        parameters_schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            parameters_schema["required"] = required
        declarations.append(
            types.FunctionDeclaration(
                name=name,
                description=data["description"],
                parameters_json_schema=parameters_schema,
            )
        )
    if not declarations:
        return []
    return [types.Tool(function_declarations=declarations)]


async def create_function_list(functions: list[Callable[..., Awaitable[Any]]], **kwargs) -> list[AsyncFunction]:
    func_list: list[AsyncFunction] = []
    for func in functions:
        name = func.__name__
        async with aiofiles.open(f"./src/prompt/__tools__/{name}.yaml", "r", encoding="utf-8") as f:
            func_info = type_validate_python(MoonlarkFunctionDefinition, yaml.safe_load(await f.read()))
        parameters: dict[str, FunctionParameter | FunctionParameterWithEnum] = {}
        for param in func_info.parameters:
            if param.enum:
                parameters[param.name] = FunctionParameterWithEnum(
                    type=param.type,
                    description=param.description.format(**kwargs),
                    required=param.required,
                    enum=set(param.enum),
                )
            else:
                parameters[param.name] = FunctionParameter(
                    type=param.type,
                    description=param.description.format(**kwargs),
                    required=param.required,
                )
        func_list.append(
            AsyncFunction(
                func=func,
                description=func_info.description.format(**kwargs),
                parameters=parameters,
            )
        )
    return func_list
