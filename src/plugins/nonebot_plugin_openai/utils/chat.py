import asyncio
import hashlib
from collections.abc import Awaitable
import traceback
import uuid

from openai.types.chat import ChatCompletion
from openai.types.chat.chat_completion import Choice

from nonebot_plugin_larklang.__main__ import get_module_name
import inspect
from openai.types.chat.chat_completion_message_function_tool_call import ChatCompletionMessageFunctionToolCall

import json
from typing import Literal, Optional, Any, AsyncGenerator, Callable, TypeVar, TypedDict, cast
from nonebot import logger
import openai
from openai.types.shared_params import FunctionDefinition
from openai.types.chat import ChatCompletionToolMessageParam, ChatCompletionFunctionToolParam
from nonebot_plugin_status_report import report_openai_history

from ..types import Messages, AsyncFunction, Message as OpenaiMessage

from ..config import config
from .message import generate_message
from .client import client
from .model_config import get_model_for_identify, is_default_model_for_identify, record_timeout_and_check_backup


def generate_function_list(func_index: dict[str, AsyncFunction]) -> list[ChatCompletionFunctionToolParam]:
    func_list = []
    for name, data in func_index.items():
        func_info = FunctionDefinition(
            name=name, description=data["description"], parameters={"type": "object", "properties": {}, "required": []}
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


T = TypeVar("T")


class ReplaceResponseStrategy(TypedDict):
    strategy: Literal["replace"]
    choice: Choice


class StopSessionStrategy(TypedDict):
    strategy: Literal["throw"]


TimeoutStrategy = ReplaceResponseStrategy | StopSessionStrategy


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
        timeout: Optional[int] = None,
        timeout_strategy: Optional[TimeoutStrategy] = None,
    ) -> None:
        self.messages: Messages = messages
        self.identify = identify
        self.func_list = generate_function_list(func_index)
        self.func_index = func_index
        self.kwargs = kwargs
        self.stop = False
        self.trace_id = uuid.uuid4().hex
        self.model = model
        self.trigger_functions = {
            "pre_function_call": pre_function_call,
            "post_function_call": post_function_call,
        }
        self.timeout_per_request = timeout
        self.timeout_strategy = timeout_strategy
        self.insert_message_queue = []

    async def fetch_llm_response(self) -> AsyncGenerator[str, None]:
        retry_count = 0
        while not self.stop:
            is_success = False
            async for message in self.request():
                yield message
                is_success = True
            if not is_success:
                retry_count += 1
                if retry_count > 3:
                    raise Exception("Failed to fetch LLM response after 3 retries")
                await asyncio.sleep(1)
            else:
                retry_count = 0
        await report_openai_history(self.messages, self.identify, self.model)

    async def request(self) -> AsyncGenerator[str, None]:
        try:
            completion = cast(
                ChatCompletion,
                await client.chat.completions.create(
                    messages=self.messages,
                    model=self.model,
                    tools=self.func_list,
                    tool_choice="auto" if self.func_list else "none",
                    extra_headers={
                        config.openai_thread_header: (t := f"{config.identify_prefix} - {self.identify}"),
                        config.openai_trace_header: self.trace_id,
                        "HTTP-Referer": f"https://{hashlib.sha256(t.encode()).hexdigest()}.moonlark.itcdt.top",
                    },
                    timeout=self.timeout_per_request,
                    **self.kwargs,
                ),
            )
            response = completion.choices[0]
        except openai.APITimeoutError as e:
            if self.timeout_strategy is None or self.timeout_strategy["strategy"] == "throw":
                raise e
            elif self.timeout_strategy["strategy"] == "replace":
                response = self.timeout_strategy["choice"]
        except IndexError:
            logger.warning(f"Response is empty, {self.messages=}")
            return
        logger.debug(f"{response=}\n{self.messages=}\n{self.model=}\n{self.func_list=}\n{completion=}")
        self.messages.append(response.message)
        if response.message.content:
            yield response.message.content
        if response.message.tool_calls:
            for request in response.message.tool_calls:
                if isinstance(request, ChatCompletionMessageFunctionToolCall):
                    await self.call_function(request.id, request.function.name, json.loads(request.function.arguments))
        else:
            # FUCK YOU OPENAI
            # 我操你妈逼谷歌
            self.stop = True
        self.messages.extend(self.insert_message_queue)
        self.insert_message_queue.clear()

    def insert_message(self, message: OpenaiMessage) -> None:
        self.insert_message_queue.append(message)

    def insert_messages(self, messages: Messages) -> None:
        self.insert_message_queue.extend(messages)

    async def call_function(self, call_id: str, name: str, params: dict[str, Any]) -> None:
        if self.trigger_functions["pre_function_call"]:
            call_id, name, params = await self.trigger_functions["pre_function_call"](call_id, name, params)
        try:
            result = await self.func_index[name]["func"](**params)
        except Exception as e:
            logger.exception(e)
            result = f"工具调用失败：{traceback.format_exc()}"
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
        use_default_message: bool,
        model: str,
        functions: Optional[list[AsyncFunction]],
        identify: str,
        pre_function_call: Optional[Callable[[str, str, dict[str, Any]], Awaitable[tuple[str, str, dict[str, Any]]]]],
        post_function_call: Optional[Callable[[T], Awaitable[T]]],
        timeout: Optional[int] = None,
        timeout_strategy: Optional[TimeoutStrategy] = None,
        record_timeout: bool = False,
        **kwargs,
    ) -> None:
        logger.debug(f"{identify=}")
        if use_default_message:
            messages.insert(0, generate_message(config.openai_default_message, "system"))
        func_index: dict[str, AsyncFunction] = {}
        if functions:
            for func in functions:
                func_index[func["func"].__name__] = func
        self.session = LLMRequestSession(
            messages,
            func_index,
            model,  # type: ignore
            kwargs,
            identify,
            pre_function_call,
            post_function_call,
            timeout,
            timeout_strategy,
        )
        self.record_timeout = record_timeout

    @classmethod
    async def create(
        cls,
        messages: Messages,
        use_default_message: bool = False,
        model: Optional[str] = None,
        functions: Optional[list[AsyncFunction]] = None,
        identify: Optional[str] = None,
        pre_function_call: Optional[
            Callable[[str, str, dict[str, Any]], Awaitable[tuple[str, str, dict[str, Any]]]]
        ] = None,
        post_function_call: Optional[Callable[[T], Awaitable[T]]] = None,
        timeout: Optional[int] = None,
        timeout_strategy: Optional[TimeoutStrategy] = None,
        record_timeout: Optional[bool] = None,
        **kwargs,
    ) -> "MessageFetcher":
        """异步创建 MessageFetcher 实例，正确处理模型配置获取"""
        if identify is None:
            stack = inspect.stack()[1]
            function_name = stack.function
            plugin_name = get_module_name(inspect.getmodule(stack[0]))
            identify = f"{plugin_name}.{function_name}"

        if model is None:
            model = await get_model_for_identify(identify)
            is_default_model = await is_default_model_for_identify(identify)
        else:
            is_default_model = False

        return cls(
            messages,
            use_default_message,
            model,
            functions,
            identify,
            pre_function_call,
            post_function_call,
            timeout,
            timeout_strategy,
            is_default_model if record_timeout is None else record_timeout,
            **kwargs,
        )

    async def fetch_last_message(self) -> str:
        # return (await self.fetch_messages())[-1]
        return [msg async for msg in self.session.fetch_llm_response()][-1]

    async def fetch_message_stream(self) -> AsyncGenerator[str, None]:
        try:
            async for msg in self.session.fetch_llm_response():
                yield msg
        except openai.APITimeoutError as e:
            if self.record_timeout:
                await record_default_model_timeout()
            raise e

    def get_messages(self) -> Messages:
        return self.session.messages


async def record_default_model_timeout() -> None:
    """
    记录默认模型超时事件

    当主模型在一小时内触发超时超过 2 次时，
    将主模型临时替换为 identify 为 Backup 的模型，持续 1 小时。
    """
    await record_timeout_and_check_backup()


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
    timeout: Optional[int] = None,
    timeout_strategy: Optional[TimeoutStrategy] = None,
    **kwargs,
) -> str:
    if identify is None:
        stack = inspect.stack()[1]
        function_name = stack.function
        plugin_name = get_module_name(inspect.getmodule(stack[0]))
        identify = f"{plugin_name}.{function_name}"

    fetcher = await MessageFetcher.create(
        messages,
        use_default_message,
        model,
        functions,
        identify,
        pre_function_call,
        post_function_call,
        timeout,
        timeout_strategy,
        **kwargs,
    )
    return await fetcher.fetch_last_message()
