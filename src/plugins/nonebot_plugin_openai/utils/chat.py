import hashlib

from nonebot_plugin_larklang.__main__ import get_module_name
import inspect
import json
from typing import Optional, Any

from nonebot import logger
from openai.types.shared_params import FunctionDefinition
from openai.types.chat import ChatCompletionToolMessageParam, ChatCompletionFunctionToolParam
from nonebot_plugin_status_report import report_openai_history

from ..types import Messages, AsyncFunction

from ..config import config
from .message import generate_message
from .client import client


def generate_function_list(func_index: dict[str, AsyncFunction]) -> list[ChatCompletionFunctionToolParam]:
    func_list = []
    for name, data in func_index.items():
        func_info = FunctionDefinition(
            name=name, description=data["description"], parameters={"type": "object", "properties": {}, "required": []}
        )
        for p_name, p_data in data["parameters"].items():
            param_info = {"type": p_data["type"], "description": p_data["description"]}
            if "enum" in p_data:
                param_info["enum"] = list(p_data["enum"])
            func_info["parameters"]["properties"][p_name] = param_info
            if p_data["required"]:
                func_info["parameters"]["required"].append(p_name)
        func_list.append(
            ChatCompletionFunctionToolParam(
                type="function",
                function=func_info,
            )
        )
    return func_list


class LLMRequestSession:

    def __init__(
        self,
        messages: Messages,
        func_index: dict[str, AsyncFunction],
        model: str,
        kwargs: dict[str, Any],
        identify: str,
    ) -> None:
        self.messages: Messages = messages
        self.identify = identify
        self.func_list = generate_function_list(func_index)
        self.func_index = func_index
        self.kwargs = kwargs
        self.stop = False
        self.result_content = []
        self.model = model

    async def fetch_llm_response(self) -> None:
        while not self.stop:
            await self.request()
        await report_openai_history(self.messages, self.identify, self.model)

    def get_last_message(self) -> str:
        return self.result_content[-1]

    async def request(self) -> None:
        response = (
            await client.chat.completions.create(
                messages=self.messages,
                model=self.model,
                tools=self.func_list,
                tool_choice="auto" if self.func_list else "none",
                extra_headers={
                    "X-Title": (t := f"Moonlark - {self.identify}"),
                    "HTTP-Referer": f"https://{hashlib.sha256(t.encode()).hexdigest()}.moonlark.itcdt.top",
                },
                **self.kwargs,
            )
        ).choices[0]
        logger.debug(f"{response=}\n{self.messages=}\n{self.model=}\n{self.func_list=}")
        self.messages.append(response.message)
        if response.message.content:
            self.result_content.append(response.message.content)
        if response.finish_reason == "tool_calls":
            for request in response.message.tool_calls:
                await self.call_function(request.id, request.function.name, json.loads(request.function.arguments))
        elif response.finish_reason == "stop":
            self.stop = True

    async def call_function(self, call_id: str, name: str, params: dict[str, Any]) -> None:
        result = await self.func_index[name]["func"](**params)
        if result is None:
            result = "success"
        logger.debug(f"函数返回: {result}")
        msg: ChatCompletionToolMessageParam = {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(result, ensure_ascii=False),
        }
        self.messages.append(msg)


class MessageFetcher:

    def __init__(
        self,
        messages: Messages,
        use_default_message: bool = False,
        model: Optional[str] = None,
        functions: Optional[list[AsyncFunction]] = None,
        identify: Optional[str] = None,
        **kwargs,
    ) -> None:
        if identify is None:
            stack = inspect.stack()[1]
            function_name = stack.function
            plugin_name = get_module_name(inspect.getmodule(stack[0]))
            identify = f"{plugin_name}.{function_name}"
        logger.debug(f"{identify=}")

        if model is None:
            model = config.model_override.get(identify, config.openai_default_model)

        if use_default_message:
            messages.insert(0, generate_message(config.openai_default_message, "system"))
        func_index: dict[str, AsyncFunction] = {}
        if functions:
            for func in functions:
                func_index[func["func"].__name__] = func
        self.session = LLMRequestSession(messages, func_index, model, kwargs, identify)

    async def fetch_last_message(self) -> str:
        return (await self.fetch_messages())[-1]

    async def fetch_all_messages(self, separation: str = "\n\n") -> str:
        return separation.join(await self.fetch_messages())

    async def fetch_messages(self) -> list[str]:
        await self.session.fetch_llm_response()
        return self.session.result_content

    def get_messages(self) -> Messages:
        return self.session.messages


async def fetch_message(
    messages: Messages,
    use_default_message: bool = False,
    model: Optional[str] = None,
    functions: Optional[list[AsyncFunction]] = None,
    identify: Optional[str] = None,
    **kwargs,
) -> str:
    if identify is None:
        stack = inspect.stack()[1]
        function_name = stack.function
        plugin_name = get_module_name(inspect.getmodule(stack[0]))
        identify = f"{plugin_name}.{function_name}"

    if model is None:
        model = config.model_override.get(identify, config.openai_default_model)

    fetcher = MessageFetcher(messages, use_default_message, model, functions, identify, **kwargs)
    return await fetcher.fetch_last_message()
