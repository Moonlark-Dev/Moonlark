"""Gemini 插件：工具调用循环、请求头与图片拦截重试的测试（mock 掉 SDK 客户端）"""

from __future__ import annotations

import base64
from typing import Any

import pytest
from google.genai import types

PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(b"\x89PNG-fake").decode("ascii")


def _text_response(text: str) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[types.Part(text=text)]),
                finish_reason=types.FinishReason.STOP,
            )
        ]
    )


def _function_call_response(name: str, args: dict[str, Any], call_id: str = "call-1") -> types.GenerateContentResponse:
    part = types.Part(function_call=types.FunctionCall(id=call_id, name=name, args=args))
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[part]),
                finish_reason=types.FinishReason.STOP,
            )
        ]
    )


def _blocked_response(reason: types.FinishReason) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[]), finish_reason=reason)]
    )


class _FakeModels:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def generate_content(
        self,
        *,
        model: str,
        contents: Any,
        config: types.GenerateContentConfig,
    ) -> types.GenerateContentResponse:
        self.calls.append({"model": model, "contents": contents, "config": config})
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _FakeAsyncModels:
    def __init__(self, models: _FakeModels) -> None:
        self.models = models


class _FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.aio = _FakeAsyncModels(_FakeModels(responses))


def _install_client(monkeypatch: pytest.MonkeyPatch, responses: list[Any]) -> _FakeClient:
    from nonebot_plugin_gemini.utils import chat as gemini_chat

    client = _FakeClient(responses)
    monkeypatch.setattr(gemini_chat, "get_client", lambda: client)
    return client


def _make_fetcher(messages: list[dict[str, Any]], **kwargs: Any) -> Any:
    from nonebot_plugin_gemini.utils.chat import MessageFetcher

    functions = kwargs.pop("functions", None)
    identify = kwargs.pop("identify", "Test")
    return MessageFetcher(messages, False, "gemini-2.5-flash", functions, identify, None, None, **kwargs)


async def _collect(fetcher: Any) -> list[Any]:
    return [message async for message in fetcher.fetch_message_stream()]


async def test_plain_text_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """普通回复：产出文本，并把 assistant 消息追加进消息列表"""
    client = _install_client(monkeypatch, [_text_response("你好喵")])
    messages = [{"role": "system", "content": "系统"}, {"role": "user", "content": "在吗"}]
    fetcher = _make_fetcher(messages)

    assert await _collect(fetcher) == ["你好喵"]
    assert messages[-1] == {"role": "assistant", "content": "你好喵"}
    # system 消息进入 system_instruction，而不是 contents
    config = client.aio.models.calls[0]["config"]
    assert config.system_instruction == "系统"


async def test_tool_call_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """工具调用：执行函数、把结果作为 tool 消息送回模型，再取最终回复"""
    client = _install_client(
        monkeypatch,
        [_function_call_response("get_weather", {"city": "杭州"}), _text_response("杭州晴")],
    )
    calls: list[dict[str, Any]] = []

    async def get_weather(city: str) -> str:
        calls.append({"city": city})
        return "晴，25℃"

    messages = [{"role": "user", "content": "杭州天气"}]
    fetcher = _make_fetcher(
        messages,
        functions=[{"func": get_weather, "description": "查询天气", "parameters": {}}],
    )

    assert await _collect(fetcher) == ["杭州晴"]
    assert calls == [{"city": "杭州"}]
    # 第一轮 assistant 记录工具调用，第二轮的请求里带上了工具返回
    assert messages[1]["role"] == "assistant"
    assert messages[1]["tool_calls"][0]["function"]["name"] == "get_weather"
    assert messages[2] == {"role": "tool", "tool_call_id": "call-1", "content": "晴，25℃"}
    second_contents = client.aio.models.calls[1]["contents"]
    assert second_contents[-1].role == "user"
    function_response = second_contents[-1].parts[0].function_response
    assert function_response is not None
    assert function_response.name == "get_weather"


async def test_tool_error_is_reported_to_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """工具抛异常时把异常信息作为工具结果返回，而不是中断整轮请求"""
    _install_client(
        monkeypatch,
        [_function_call_response("boom", {}), _text_response("失败了")],
    )

    async def boom() -> str:
        raise RuntimeError("炸了")

    messages = [{"role": "user", "content": "试试"}]
    fetcher = _make_fetcher(
        messages,
        functions=[{"func": boom, "description": "会报错的工具", "parameters": {}}],
    )

    assert await _collect(fetcher) == ["失败了"]
    assert "炸了" in messages[2]["content"]


async def test_trace_and_thread_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    """请求头里带上 Thread / Trace 标识（AxonHub 依赖它们做链路追踪）"""
    client = _install_client(monkeypatch, [_text_response("ok")])
    fetcher = _make_fetcher([{"role": "user", "content": "hi"}])

    await _collect(fetcher)

    headers = client.aio.models.calls[0]["config"].http_options.headers
    assert headers is not None
    assert headers["AH-Thread-Id"] == "Moonlark - Test"
    assert headers["AH-Trace-Id"] == fetcher.session.trace_id


async def test_custom_trace_id_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    """调用方可以覆盖 trace id（Chat 用 session:context_index 作为 trace id）"""
    client = _install_client(monkeypatch, [_text_response("ok")])
    fetcher = _make_fetcher([{"role": "user", "content": "hi"}])
    fetcher.session.set_custom_trace_id("qq_1:3")

    await _collect(fetcher)

    headers = client.aio.models.calls[0]["config"].http_options.headers
    assert headers is not None
    assert headers["AH-Trace-Id"] == "qq_1:3"


async def test_blocked_image_is_replaced_and_request_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """图片被拦截：回调替换图片后重试，且重试请求里不再包含图片"""
    client = _install_client(
        monkeypatch,
        [_blocked_response(types.FinishReason.IMAGE_SAFETY), _text_response("看到了")],
    )
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "这是什么"},
                {"type": "image_url", "image_url": {"url": PNG_DATA_URL}},
            ],
        }
    ]
    replaced: list[int] = []

    async def on_image_blocked(session: Any) -> bool:
        replaced.append(session.request_start_index)
        messages[0]["content"][1] = {"type": "text", "text": "[图片(img_1): 一只猫]"}
        return True

    fetcher = _make_fetcher(messages, on_image_blocked=on_image_blocked)

    assert await _collect(fetcher) == ["看到了"]
    assert replaced == [1]
    assert len(client.aio.models.calls) == 2
    retried_parts = client.aio.models.calls[1]["contents"][0].parts
    assert all(part.inline_data is None for part in retried_parts)
    assert fetcher.session.image_block_retries == 1


async def test_blocked_image_gives_up_after_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """图片替换后仍被拦截时按重试上限放弃，不再无限重试"""
    client = _install_client(
        monkeypatch,
        [_blocked_response(types.FinishReason.IMAGE_SAFETY) for _ in range(5)],
    )
    messages = [
        {
            "role": "user",
            "content": [{"type": "image_url", "image_url": {"url": PNG_DATA_URL}}],
        }
    ]

    async def on_image_blocked(_session: Any) -> bool:
        return True

    fetcher = _make_fetcher(messages, on_image_blocked=on_image_blocked)

    assert await _collect(fetcher) == []
    # 首次请求 + 默认 2 次重试
    assert len(client.aio.models.calls) == 3
    assert fetcher.session.stop is True


async def test_blocked_without_callback_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有回调时被拦截的结果不会触发重试，只记录并结束本轮"""
    client = _install_client(monkeypatch, [_blocked_response(types.FinishReason.SAFETY)])
    fetcher = _make_fetcher([{"role": "user", "content": "hi"}])

    assert await _collect(fetcher) == []
    assert len(client.aio.models.calls) == 1


async def test_prompt_feedback_block_is_treated_as_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """promptFeedback.blockReason 同样是拦截，需要走同一套恢复流程"""
    _install_client(
        monkeypatch,
        [
            types.GenerateContentResponse(
                prompt_feedback=types.GenerateContentResponsePromptFeedback(
                    block_reason=types.BlockedReason.IMAGE_SAFETY
                ),
                candidates=[],
            ),
            _text_response("恢复了"),
        ],
    )
    called: list[bool] = []

    async def on_image_blocked(_session: Any) -> bool:
        called.append(True)
        return True

    messages = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": PNG_DATA_URL}}]}]
    fetcher = _make_fetcher(messages, on_image_blocked=on_image_blocked)

    assert await _collect(fetcher) == ["恢复了"]
    assert called == [True]


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("带\x00NUL 的文本", "带NUL 的文本"),
    ],
)
async def test_nul_is_stripped(monkeypatch: pytest.MonkeyPatch, content: str, expected: str) -> None:
    """请求体里的 NUL 会被剔除（网关会拒绝含 NUL 的请求体）"""
    client = _install_client(monkeypatch, [_text_response("ok")])
    fetcher = _make_fetcher([{"role": "user", "content": content}])

    await _collect(fetcher)

    parts = client.aio.models.calls[0]["contents"][0].parts
    assert parts[0].text == expected
