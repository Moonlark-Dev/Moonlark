"""Gemini 工具调用循环

与 ``nonebot_plugin_openai.utils.chat`` 提供同样的接口（``LLMRequestSession`` /
``MessageFetcher`` / ``fetch_message`` / ``fetch_json``），因此调用方只需要在创建
fetcher 时换成这个模块，其余代码不用改：

- 消息列表始终是 OpenAI 风格的 dict（见 ``utils/convert.py``），每次请求前再转换成
  Gemini 的 ``Content``；
- 每轮请求里自动执行模型要求的工具调用，并把工具返回作为 ``function_response`` 送回
  模型，直到模型不再要求调用工具；
- 请求头里写入 AxonHub 需要的 Thread Id / Trace Id（可配置多个 Trace Id 头）；
- 图片被 Gemini 安全策略拦截（``finish_reason`` 为 ``IMAGE_SAFETY`` 等）时，调用调用方
  提供的 ``on_image_blocked`` 回调把图片替换成文字描述后重试。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import json
import re
import traceback
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, Generic, Optional, TypeVar

from google.genai import types
from nonebot import logger
from nonebot.compat import type_validate_json
from nonebot_plugin_larklang.__main__ import get_module_name
from pydantic import BaseModel, ValidationError

from ..config import config
from ..exceptions import EmptyReplyContent
from ..types import AsyncFunction, Message as GeminiMessage, Messages, TimeoutStrategy
from .client import get_client
from .convert import THOUGHT_SIGNATURE_KEY, convert_messages
from .functions import generate_function_list
from .message import generate_message
from .model_config import get_model_for_identify

T = TypeVar("T")
T2 = TypeVar("T2", bound=BaseModel)

# 这些 finish_reason 表示整轮候选被安全策略拦下，其中图片相关的原因可以通过
# 「把图片换成文字描述后重试」来恢复
BLOCKED_FINISH_REASONS: frozenset[types.FinishReason] = frozenset(
    {
        types.FinishReason.SAFETY,
        types.FinishReason.PROHIBITED_CONTENT,
        types.FinishReason.BLOCKLIST,
        types.FinishReason.IMAGE_SAFETY,
        types.FinishReason.IMAGE_PROHIBITED_CONTENT,
        types.FinishReason.IMAGE_OTHER,
        types.FinishReason.SPII,
    }
)

BLOCKED_BY_PROMPT_FREASONS: frozenset[types.BlockedReason] = frozenset(
    {
        types.BlockedReason.SAFETY,
        types.BlockedReason.PROHIBITED_CONTENT,
        types.BlockedReason.BLOCKLIST,
        types.BlockedReason.IMAGE_SAFETY,
        types.BlockedReason.JAILBREAK,
    }
)


def _timeout_errors() -> tuple[type[BaseException], ...]:
    """SDK 底层可能抛出的超时异常（新版 SDK 默认使用 httpx2）"""
    errors: tuple[type[BaseException], ...] = (asyncio.TimeoutError, TimeoutError)
    for module_name in ("httpx", "httpx2"):
        try:
            module = __import__(module_name)
        except ImportError:  # pragma: no cover - 取决于安装的 SDK
            continue
        exception = getattr(module, "TimeoutException", None)
        if isinstance(exception, type):
            errors += (exception,)
    return errors


TIMEOUT_ERRORS = _timeout_errors()


def _strip_nul(text: str) -> str:
    """剔除 NUL（U+0000）：网关会把含它的请求体整次写成 {"message": "invalid text"}"""
    return text.replace("\x00", "")


def _supports_thinking_level(model: str) -> bool:
    """Gemini 3 及以后使用 thinking_level，更早的模型使用 thinking_budget"""
    return any(prefix in model for prefix in ("gemini-3", "gemini-4"))


def build_thinking_config(model: str, reasoning_effort: Optional[str]) -> Optional[types.ThinkingConfig]:
    """把 OpenAI 风格的 reasoning_effort 映射成 Gemini 的 thinking 配置

    映射表来自插件配置，默认留空表示不向模型传递 thinking 配置（不同模型支持的字段
    不一样，传错会让请求直接失败）。
    """
    if not reasoning_effort:
        return None
    effort = reasoning_effort.lower()
    if _supports_thinking_level(model):
        level = config.gemini_thinking_levels.get(effort)
        return types.ThinkingConfig(thinking_level=level) if level else None
    budget = config.gemini_thinking_budgets.get(effort)
    return types.ThinkingConfig(thinking_budget=budget) if budget is not None else None


def _extract_signature(part: types.Part) -> Optional[bytes]:
    signature = getattr(part, "thought_signature", None)
    return signature if isinstance(signature, bytes) and signature else None


class GeminiRequestSession(Generic[T2]):
    """一次对话请求的会话：负责请求、工具调用循环与消息列表维护"""

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
        reasoning_effort: Optional[str] = None,
        response_format: Optional[type[T2]] = None,
        on_tool_round_complete: Optional[Callable[[], Awaitable[None]]] = None,
        on_image_blocked: Optional[Callable[["GeminiRequestSession[T2]"], Awaitable[bool]]] = None,
    ) -> None:
        self.messages: Messages = messages
        self.identify = identify
        self.on_tool_round_complete = on_tool_round_complete
        self.on_image_blocked = on_image_blocked
        self.func_list = generate_function_list(func_index)
        self.func_index = func_index
        # tool_choice 是 OpenAI 的参数，Gemini 通过 tool_config 配置；这里保持接口一致
        self.tool_choice = kwargs.pop("tool_choice", "auto")
        self.kwargs = kwargs
        self.stop = False
        self.trace_id = uuid.uuid4().hex
        self.model = model
        self.trigger_functions = {
            "pre_function_call": pre_function_call,
            "post_function_call": post_function_call,
        }
        self.reasoning_effort = reasoning_effort
        self.has_tool_calls: bool = False
        self.response_format = response_format
        self.timeout_per_request = timeout
        self.timeout_strategy = timeout_strategy
        self.insert_message_queue: list[GeminiMessage] = []
        self._content_yielded = False
        self._in_request: bool = False
        self._this_round_success = False
        self.last_response: Optional[types.GenerateContentResponse] = None
        # 本次请求（整个工具调用循环）开始时消息列表的长度：之后的都是本轮新加的消息
        self._request_start_index: int = len(messages)
        self._image_block_retries: int = 0
        self.max_image_block_retries: int = max(0, config.gemini_image_block_retries)

    # ------------------------------------------------------------------
    # 基本信息
    # ------------------------------------------------------------------

    def set_custom_trace_id(self, trace_id: str) -> None:
        self.trace_id = trace_id

    @property
    def request_start_index(self) -> int:
        """本轮请求开始时消息列表的长度（本轮新加消息的起始下标）"""
        return self._request_start_index

    @property
    def image_block_retries(self) -> int:
        return self._image_block_retries

    # ------------------------------------------------------------------
    # 请求
    # ------------------------------------------------------------------

    async def fetch_llm_response(self) -> AsyncGenerator[T2 | str, None]:
        retry_count = 0
        self._in_request = True
        try:
            while not self.stop:
                content_yielded = False
                async for message in self.request():
                    yield message
                    content_yielded = True
                if not content_yielded and not self._this_round_success:
                    retry_count += 1
                    if retry_count > 3:
                        raise Exception("Failed to fetch LLM response after 3 retries")
                    await asyncio.sleep(1)
                else:
                    retry_count = 0
        finally:
            self._in_request = False

    def _build_extra_headers(self) -> dict[str, str]:
        """构建请求头：Thread 标识 + 多个 Trace Id 头 + 溯源 Referer"""
        thread = f"{config.identify_prefix} - {self.identify}"
        headers: dict[str, str] = {
            config.gemini_thread_header: thread,
            "HTTP-Referer": f"https://{hashlib.sha256(thread.encode()).hexdigest()}.moonlark.itcdt.top",
        }
        for header in config.gemini_trace_headers:
            headers[header] = self.trace_id
        return headers

    def _build_http_options(self) -> types.HttpOptions:
        timeout = self.timeout_per_request * 1000 if self.timeout_per_request else None
        return types.HttpOptions(headers=self._build_extra_headers(), timeout=timeout)

    def _build_config(self, system_instruction: Optional[str]) -> types.GenerateContentConfig:
        kwargs = dict(self.kwargs)
        for key in ("system_instruction", "tools", "http_options", "automatic_function_calling", "thinking_config"):
            kwargs.pop(key, None)
        allowed = set(types.GenerateContentConfig.model_fields)
        unknown = sorted(key for key in kwargs if key not in allowed)
        if unknown:
            logger.warning(f"[{self.identify}] 忽略 Gemini 不支持的请求参数: {', '.join(unknown)}")
        kwargs = {key: value for key, value in kwargs.items() if key in allowed}
        generate_config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=self.func_list or None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            http_options=self._build_http_options(),
            **kwargs,
        )
        thinking_config = build_thinking_config(self.model, self.reasoning_effort)
        if thinking_config is not None:
            generate_config.thinking_config = thinking_config
        return generate_config

    async def create_completion(self) -> types.GenerateContentResponse:
        system_instruction, contents = convert_messages(self.messages)
        if not contents:
            raise EmptyReplyContent("没有可发送给 Gemini 的消息")
        generate_config = self._build_config(system_instruction)
        return await get_client().aio.models.generate_content(
            model=self.model,
            contents=contents,
            config=generate_config,
        )

    def _blocked_reason(self, response: types.GenerateContentResponse) -> Optional[str]:
        """返回拦截原因；没有被拦截时返回 None"""
        prompt_feedback = response.prompt_feedback
        if prompt_feedback is not None and prompt_feedback.block_reason in BLOCKED_BY_PROMPT_FREASONS:
            return f"prompt {prompt_feedback.block_reason} {prompt_feedback.block_reason_message or ''}".strip()
        candidate = response.candidates[0] if response.candidates else None
        if candidate is not None and candidate.finish_reason in BLOCKED_FINISH_REASONS:
            return f"finish_reason {candidate.finish_reason}"
        return None

    async def _generate_with_image_recovery(self) -> types.GenerateContentResponse:
        """请求模型；结果被安全策略拦截时尝试替换图片后重试"""
        response = await self.create_completion()
        while True:
            reason = self._blocked_reason(response)
            if reason is None:
                return response
            logger.warning(f"[{self.identify}] Gemini 返回了被拦截的结果（{reason}）")
            if self.on_image_blocked is None:
                return response
            if self._image_block_retries >= self.max_image_block_retries:
                logger.warning(f"[{self.identify}] 图片拦截重试次数已达上限（{self.max_image_block_retries}）")
                return response
            self._image_block_retries += 1
            if not await self.on_image_blocked(self):
                logger.warning(f"[{self.identify}] 没有可替换的图片，放弃重试")
                return response
            logger.info(
                f"[{self.identify}] 已把被拦截的图片替换为文本描述，"
                f"重新请求模型（第 {self._image_block_retries} 次）",
            )
            response = await self.create_completion()

    def _parse_response(
        self, response: types.GenerateContentResponse
    ) -> tuple[Optional[str], list[dict[str, Any]], Optional[types.FinishReason]]:
        """提取文本、工具调用与 finish_reason"""
        candidate = response.candidates[0] if response.candidates else None
        finish_reason = candidate.finish_reason if candidate is not None else None
        texts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        parts = candidate.content.parts if candidate is not None and candidate.content is not None else None
        for part in parts or []:
            if getattr(part, "thought", False):
                # 思考内容不进入对话上下文
                continue
            function_call = getattr(part, "function_call", None)
            if function_call is not None:
                call_id = function_call.id or uuid.uuid4().hex
                arguments = function_call.args or {}
                entry: dict[str, Any] = {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": function_call.name or "",
                        "arguments": json.dumps(arguments, ensure_ascii=False, default=str),
                    },
                }
                signature = _extract_signature(part)
                if signature:
                    entry[THOUGHT_SIGNATURE_KEY] = base64.b64encode(signature).decode("ascii")
                tool_calls.append(entry)
            elif part.text:
                texts.append(part.text)
        text = _strip_nul("".join(texts)) if texts else None
        return (text or None), tool_calls, finish_reason

    async def request(self) -> AsyncGenerator[T2 | str, None]:
        self._this_round_success = False
        try:
            logger.info(f"[{self.identify}] 正在请求模型 {self.model} ...")
            response = await self._generate_with_image_recovery()
            self.last_response = response
        except TIMEOUT_ERRORS as e:
            if self.timeout_strategy is None or self.timeout_strategy["strategy"] == "throw":
                raise e
            response = self.timeout_strategy["choice"]
        except EmptyReplyContent:
            logger.warning("请求取得了空回复")
            self.stop = True
            return
        except Exception as e:
            logger.exception(e)
            raise
        text, tool_calls, finish_reason = self._parse_response(response)
        logger.debug(f"[{self.identify}] finish_reason={finish_reason}, tool_calls={len(tool_calls)}")
        if text is None and not tool_calls:
            # 被安全策略拦下或模型只输出了思考内容：本轮没有任何可用输出，直接结束
            if finish_reason in BLOCKED_FINISH_REASONS:
                logger.warning(f"[{self.identify}] 模型输出被拦截（{finish_reason}），结束本轮请求")
                self.stop = True
            else:
                logger.warning(f"[{self.identify}] 模型返回了空回复（finish_reason={finish_reason}）")
            return

        assistant_message: dict[str, Any] = {"role": "assistant", "content": text}
        if tool_calls:
            assistant_message["tool_calls"] = tool_calls
        self.messages.append(assistant_message)
        if text:
            self._content_yielded = True
            self._this_round_success = True
            yield text
        if tool_calls:
            self._this_round_success = True
            for entry in tool_calls:
                await self.call_function(
                    entry["id"],
                    entry["function"]["name"],
                    json.loads(entry["function"]["arguments"] or "{}"),
                )
            if not self._content_yielded and self.on_tool_round_complete:
                await self.on_tool_round_complete()
        elif not self.insert_message_queue:
            self.stop = True
        self.messages.extend(self.insert_message_queue)
        self.insert_message_queue.clear()

    def insert_message(self, message: GeminiMessage) -> None:
        if self._in_request:
            self.insert_message_queue.append(message)
        else:
            self.messages.append(message)

    def insert_messages(self, messages: Messages) -> None:
        if self._in_request:
            self.insert_message_queue.extend(messages)
        else:
            self.messages.extend(messages)

    async def call_function(self, call_id: str, name: str, params: dict[str, Any]) -> None:
        logger.debug(f"[{self.identify}] Calling function {name} with params {params}")
        self.has_tool_calls = True
        if self.trigger_functions["pre_function_call"]:
            call_id, name, params = await self.trigger_functions["pre_function_call"](call_id, name, params)
        function = self.func_index.get(name)
        if function is None:
            result: Any = f"工具调用失败：未知工具 {name}"
        else:
            try:
                result = await function["func"](**params)
            except Exception as e:
                logger.exception(e)
                # 使用 format_exception_only 排除 traceback，只保留异常类型和消息
                last_line = traceback.format_exception_only(type(e), e)[-1].strip()
                result = f"工具调用失败：{last_line}"
        if self.trigger_functions["post_function_call"]:
            result = await self.trigger_functions["post_function_call"](result)
        if result is None:
            result = "success"
        logger.debug(f"函数返回: {result}")
        if isinstance(result, str):
            content = result
        else:
            content = json.dumps(result, ensure_ascii=False)
        content = _strip_nul(content)
        self.messages.append({"role": "tool", "tool_call_id": call_id, "content": content})


class MessageFetcher(Generic[T2]):
    """与 OpenAI 插件同名的入口：负责创建会话并暴露流式/一次性接口"""

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
        reasoning_effort: Optional[str] = None,
        response_format: Optional[type[T2]] = None,
        on_tool_round_complete: Optional[Callable[[], Awaitable[None]]] = None,
        on_image_blocked: Optional[Callable[[GeminiRequestSession], Awaitable[bool]]] = None,
        **kwargs,
    ) -> None:
        logger.debug(f"{identify=}")
        if use_default_message and config.gemini_default_message:
            messages.insert(0, generate_message(config.gemini_default_message, "system"))
        func_index: dict[str, AsyncFunction] = {}
        if functions:
            for func in functions:
                func_index[func["func"].__name__] = func
        self.session = GeminiRequestSession(
            messages,
            func_index,
            model,
            kwargs,
            identify,
            pre_function_call,
            post_function_call,
            timeout,
            timeout_strategy,
            reasoning_effort,
            response_format,
            on_tool_round_complete,
            on_image_blocked,
        )

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
        reasoning_effort: Optional[str] = None,
        response_format: Optional[type[T2]] = None,
        on_tool_round_complete: Optional[Callable[[], Awaitable[None]]] = None,
        on_image_blocked: Optional[Callable[[GeminiRequestSession], Awaitable[bool]]] = None,
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
            reasoning_effort,
            response_format,
            on_tool_round_complete,
            on_image_blocked,
            **kwargs,
        )

    async def fetch_last_message(self) -> T2 | str:
        return [msg async for msg in self.session.fetch_llm_response()][-1]

    async def fetch_message_stream(self) -> AsyncGenerator[T2 | str, None]:
        async for msg in self.session.fetch_llm_response():
            yield msg

    def get_messages(self) -> Messages:
        return self.session.messages


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
    reasoning_effort: Optional[str] = None,
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
        reasoning_effort,
        **kwargs,
    )
    return await fetcher.fetch_last_message()


def strip_json_codeblock(text: str) -> str:
    stripped = text.strip()
    m = re.match(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", stripped, re.DOTALL)
    if m:
        return m.group(1).strip()
    return stripped


async def fetch_json(
    messages: Messages,
    response_format: type[T2],
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
    reasoning_effort: Optional[str] = None,
    formatter_max_retry: int = 3,
    **kwargs,
) -> T2:
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
        reasoning_effort,
        **kwargs,
    )

    retry_count = 0
    async for message in fetcher.fetch_message_stream():
        try:
            return type_validate_json(response_format, strip_json_codeblock(message))
        except ValidationError as e:
            if retry_count >= formatter_max_retry:
                raise e
            retry_count += 1
            fetcher.session.insert_message(generate_message(str(e), "user"))
    raise ValueError("No valid response found")
