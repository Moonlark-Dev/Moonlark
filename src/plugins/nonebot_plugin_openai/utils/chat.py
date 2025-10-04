from datetime import datetime, timedelta
import hashlib
from collections.abc import Awaitable

from nonebot_plugin_larklang.__main__ import get_module_name
import inspect
import json
from typing import Optional, Any, AsyncGenerator, Callable, TypeVar, cast
from openai.types.chat import ChatCompletionMessage
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


T = TypeVar("T")

from openai.types.chat import ChatCompletion
from openai.types.chat.chat_completion import Choice


class LLMRequestSession:

    def __init__(
        self,
        messages: Messages,
        func_index: dict[str, AsyncFunction],
        model: str,
        kwargs: dict[str, Any],
        identify: str,
        pre_function_call: Optional[
            Callable[[str, str, dict[str, Any]], Awaitable[tuple[str, str, dict[str, Any]]]]
        ] = None,
        post_function_call: Optional[Callable[[T], Awaitable[T]]] = None,
        timeout_per_request: Optional[int] = None,
        timeout_response: Optional[Choice] = None,
    ) -> None:
        self.messages: Messages = messages
        self.identify = identify
        self.func_list = generate_function_list(func_index)
        self.func_index = func_index
        self.kwargs = kwargs
        self.stop = False
        self.timeout_state = False
        self.model = model
        self.trigger_functions = {
            "pre_function_call": pre_function_call,
            "post_function_call": post_function_call,
        }
        self.timeout_per_request = timeout_per_request
        self.timeout_response = timeout_response

    async def fetch_llm_response(self) -> AsyncGenerator[str, None]:
        while not self.stop:
            async for message in self.request():
                yield message
        await report_openai_history(self.messages, self.identify, self.model)

    async def request(self) -> AsyncGenerator[str, None]:
        completion = cast(
            ChatCompletion,
            await client.chat.completions.create(
                messages=self.messages,
                model=self.model,
                tools=self.func_list,
                tool_choice="auto" if self.func_list else "none",
                extra_headers={
                    "X-Title": (t := f"{config.identify_prefix} - {self.identify}"),
                    "HTTP-Referer": f"https://{hashlib.sha256(t.encode()).hexdigest()}.moonlark.itcdt.top",
                },
                **self.kwargs,
            ),
        )
        response = completion.choices[0]
        if self.timeout_per_request and datetime.now() - datetime.fromtimestamp(completion.created) > timedelta(
            seconds=self.timeout_per_request
        ):
            self.stop = True
            if self.timeout_response:
                response = self.timeout_response
        logger.debug(f"{response=}\n{self.messages=}\n{self.model=}\n{self.func_list=}\n{completion=}")
        self.messages.append(response.message)
        if response.message.content:
            yield response.message.content
        if response.message.tool_calls:
            for request in response.message.tool_calls:
                await self.call_function(request.id, request.function.name, json.loads(request.function.arguments))
        elif response.finish_reason in ["stop", "eos"]:
            self.stop = True

    async def call_function(self, call_id: str, name: str, params: dict[str, Any]) -> None:
        if self.trigger_functions["pre_function_call"]:
            call_id, name, params = await self.trigger_functions["pre_function_call"](call_id, name, params)
        result = await self.func_index[name]["func"](**params)
        if self.trigger_functions["post_function_call"]:
            result = await self.trigger_functions["post_function_call"](result)
        if result is None:
            result = "success"
        logger.debug(f"函数返回: {result}")
        if isinstance(result, str):
            content = result
        else:
            content = json.dumps(result, ensure_ascii=False)
        msg: ChatCompletionToolMessageParam = {
            "role": "tool",
            "tool_call_id": call_id,
            "content": content,
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
        pre_function_call: Optional[
            Callable[[str, str, dict[str, Any]], Awaitable[tuple[str, str, dict[str, Any]]]]
        ] = None,
        post_function_call: Optional[Callable[[T], Awaitable[T]]] = None,
        timeout_per_request: Optional[int] = None,
        timeout_response: Optional[Choice] = None,
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
        self.session = LLMRequestSession(
            messages,
            func_index,
            model,
            kwargs,
            identify,
            pre_function_call,
            post_function_call,
            timeout_per_request,
            timeout_response,
        )

    async def fetch_last_message(self) -> str:
        # return (await self.fetch_messages())[-1]
        return [msg async for msg in self.session.fetch_llm_response()][-1]

    async def fetch_message_stream(self) -> AsyncGenerator[str, None]:
        async for msg in self.session.fetch_llm_response():
            yield msg

    def get_messages(self) -> Messages:
        return self.session.messages

    def is_time_outed(self) -> bool:
        return self.session.timeout_state


async def fetch_message(
    messages: Messages,
    use_default_message: bool = False,
    model: Optional[str] = None,
    functions: Optional[list[AsyncFunction]] = None,
    identify: Optional[str] = None,
    pre_function_call: Optional[
        Callable[[str, str, dict[str, Any]], Awaitable[tuple[str, str, dict[str, Any]]]]
    ] = None,
    post_function_call: Optional[Callable[[T], Awaitable[T]]] = None,
    timeout_per_request: Optional[int] = None,
    timeout_response: Optional[Choice] = None,
    **kwargs,
) -> str:
    if identify is None:
        stack = inspect.stack()[1]
        function_name = stack.function
        plugin_name = get_module_name(inspect.getmodule(stack[0]))
        identify = f"{plugin_name}.{function_name}"

    if model is None:
        model = config.model_override.get(identify, config.openai_default_model)

    fetcher = MessageFetcher(
        messages,
        use_default_message,
        model,
        functions,
        identify,
        pre_function_call,
        post_function_call,
        timeout_per_request,
        timeout_response,
        **kwargs,
    )
    return await fetcher.fetch_last_message()
