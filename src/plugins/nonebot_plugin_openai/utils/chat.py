import json
from typing import Optional, Any

from nonebot import logger
from openai.types.chat import ChatCompletionToolMessageParam

from ..types import Messages, AsyncFunction

from ..config import config
from .message import generate_message
from .client import client

def generate_function_list(func_index: dict[str,AsyncFunction]) -> list[dict[str, Any]]:
    func_list = []
    for name, data in func_index.items():
        func_info = {
            "type": "function",
            "name": name,
            "description": data["description"],
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
        for p_name, p_data in data["parameters"].items():
            param_info = {
                "type": p_data["type"],
                "description": p_data["description"]
            }
            if "enum" in p_data:
                param_info["enum"] = list(p_data["enum"])
            func_info["parameters"]["properties"][p_name] = param_info
            if p_data["required"]:
                func_info["parameters"]["required"].append(p_name)
        func_list.append(func_info)
    return func_list

class LLMRequestSession:

    def __init__(self, messages: Messages, func_index: dict[str, AsyncFunction], model: str, kwargs: dict[str, Any]) -> None:
        self.messages: Messages = messages
        self.func_list = generate_function_list(func_index)
        self.func_index = func_index
        self.kwargs = kwargs
        self.result_string = ""
        self.model = model

    async def fetch_llm_response(self) -> str:
        while not self.result_string:
            await self.request()
        return self.result_string

    async def request(self) -> None:
        response = (await client.chat.completions.create(
            messages=self.messages,
            model=self.model,
            tools=self.func_list,
            **self.kwargs
        )).choices[0]
        logger.debug(f"{response=} {self.messages=} {self.model=}")
        self.messages.append(response.message)
        if response.finish_reason == "tool_calls":
            for request in response.message.tool_calls:
                await self.call_function(request.id, request.function, json.loads(request.parameters))
        elif response.finish_reason == "stop":
            self.result_string = response.message.content



    async def call_function(self, call_id: str, name: str, params: dict[str, Any]) -> None:
        result = await self.func_index[name]["func"](**params)
        if result is None:
            result = "success"
        msg: ChatCompletionToolMessageParam = {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(result)
        }
        self.messages.append(msg)


async def fetch_message(
    messages: Messages,
    use_default_message: bool = False,
    model: str = config.openai_default_model,
    functions: Optional[list[AsyncFunction]] = None,
    **kwargs,
) -> str:
    if use_default_message:
        messages.insert(0, generate_message(config.openai_default_message, "system"))
    func_index: dict[str, AsyncFunction] = {}
    if functions:
        for func in functions:
            func_index[func.__name__] = func
    session = LLMRequestSession(messages, func_index, model, kwargs)
    return await session.fetch_llm_response()

class MessageFetcher:

    def __init__(
            self,
            messages: Messages,
            use_default_message: bool = False,
            model: str = config.openai_default_model,
            functions: Optional[list[AsyncFunction]] = None,
            **kwargs
    ) -> None:
        if use_default_message:
            messages.insert(0, generate_message(config.openai_default_message, "system"))
        func_index: dict[str, AsyncFunction] = {}
        if functions:
            for func in functions:
                func_index[func.__name__] = func
        self.session = LLMRequestSession(messages, func_index, model, kwargs)

    async def fetch(self) -> str:
        return await self.session.fetch_llm_response()

    def get_messages(self) -> Messages:
        return self.session.messages


