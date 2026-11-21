"""Gemini 流式请求的回归测试

覆盖 ``nonebot_plugin_gemini.utils.chat`` 的流式路径：正文增量、工具调用、
被安全策略拦截时的收尾，以及转出的分片能否被 Chat 的私聊流式发送器消费。

Gemini API 不下发 ``partial_args``（只有 Vertex AI 支持），``function_call`` 的参数
是整段到达的，所以这里的工具调用分片只有一段。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from google.genai import types


def _chunk(
    parts: list[types.Part] | None = None,
    finish_reason: types.FinishReason | None = None,
) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=parts or []),
                finish_reason=finish_reason,
            )
        ]
    )


async def _stream(chunks: list[types.GenerateContentResponse]) -> Any:
    for chunk in chunks:
        yield chunk


class FakeModels:
    def __init__(self, streams: list[Any]) -> None:
        self._streams = list(streams)
        self.requests: list[dict[str, Any]] = []

    async def generate_content_stream(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return self._streams.pop(0)


def _install_client(monkeypatch: pytest.MonkeyPatch, streams: list[Any]) -> FakeModels:
    from nonebot_plugin_gemini.utils import chat as chat_module

    models = FakeModels(streams)
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    monkeypatch.setattr(chat_module, "get_client", lambda: client)
    return models


def _send_message_function(calls: list[str]) -> dict[str, Any]:
    async def send_message(message_content: str) -> str:
        calls.append(message_content)
        return "工具结果"

    return {
        "func": send_message,
        "description": "发送消息",
        "parameters": {
            "message_content": {"type": "string", "description": "消息内容", "required": True},
        },
    }


def _make_session(function: dict[str, Any] | None = None, stream: bool = True, **kwargs: Any) -> Any:
    from nonebot_plugin_gemini.utils.chat import GeminiRequestSession
    from nonebot_plugin_gemini.utils.message import generate_message

    func_index = {function["func"].__name__: function} if function is not None else {}
    return GeminiRequestSession(
        [generate_message("hi", "user")],
        func_index,
        "test-model",
        {},
        "Test",
        stream=stream,
        **kwargs,
    )


async def test_gemini_stream_yields_text_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    """流式请求逐片产出正文，收尾时追加 assistant 消息并下发结束分片"""
    _install_client(
        monkeypatch,
        [
            _stream(
                [
                    _chunk([types.Part(text="你")]),
                    _chunk([types.Part(text="好")], types.FinishReason.STOP),
                ]
            )
        ],
    )
    forwarded: list[Any] = []
    session = _make_session(on_stream_chunk=AsyncMock(side_effect=forwarded.append))

    outputs = [message async for message in session.fetch_llm_response()]

    assert outputs == ["你", "好"]
    assert session.messages[-1] == {"role": "assistant", "content": "你好"}
    # 两个正文分片 + 一个结束分片
    assert [chunk.choices[0].delta.content for chunk in forwarded] == ["你", "好", None]
    assert forwarded[-1].choices[0].finish_reason == "stop"


async def test_gemini_stream_executes_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """工具参数整段到达：作为单个分片转出，流结束后执行工具调用"""
    calls: list[str] = []
    function = _send_message_function(calls)
    _install_client(
        monkeypatch,
        [
            _stream(
                [
                    _chunk(
                        [
                            types.Part(
                                function_call=types.FunctionCall(
                                    id="call-1",
                                    name="send_message",
                                    args={"message_content": "你好"},
                                )
                            )
                        ],
                        types.FinishReason.STOP,
                    )
                ]
            ),
            _stream([_chunk([types.Part(text="好")], types.FinishReason.STOP)]),
        ],
    )
    forwarded: list[Any] = []
    session = _make_session(function, on_stream_chunk=AsyncMock(side_effect=forwarded.append))

    outputs = [message async for message in session.fetch_llm_response()]

    assert outputs == ["好"]
    assert calls == ["你好"]
    # 工具调用分片带完整参数，且最后一个分片标记为 tool_calls
    delta = forwarded[0].choices[0].delta
    assert delta.tool_calls[0].function.name == "send_message"
    assert delta.tool_calls[0].function.arguments == '{"message_content": "你好"}'
    assert forwarded[0].choices[0].finish_reason is None
    assert forwarded[1].choices[0].finish_reason == "tool_calls"
    # 工具调用与工具返回按 OpenAI 消息格式写回消息列表
    assert session.messages[1]["role"] == "assistant"
    assert session.messages[1]["tool_calls"][0]["function"]["name"] == "send_message"
    assert session.messages[1]["tool_calls"][0]["id"] == "call-1"
    assert session.messages[2] == {"role": "tool", "tool_call_id": "call-1", "content": "工具结果"}
    assert session.messages[3]["content"] == "好"


async def test_gemini_stream_blocked_output_is_not_appended(monkeypatch: pytest.MonkeyPatch) -> None:
    """被安全策略拦下的流式结果不追加 assistant 消息，直接结束本轮"""
    _install_client(monkeypatch, [_stream([_chunk([], types.FinishReason.IMAGE_SAFETY)])])
    session = _make_session(on_stream_chunk=AsyncMock())

    outputs = [message async for message in session.fetch_llm_response()]

    assert outputs == []
    assert session.stop is True
    assert len(session.messages) == 1


async def test_gemini_stream_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有开启 stream 时仍然走非流式接口"""
    from nonebot_plugin_gemini.utils import chat as chat_module

    calls: list[str] = []
    session = _make_session(_send_message_function(calls), stream=False)

    async def fake_completion() -> types.GenerateContentResponse:
        return _chunk([types.Part(text="你好")], types.FinishReason.STOP)

    async def fake_stream_completion() -> Any:  # pragma: no cover - 不应该被调用
        raise AssertionError("未开启 stream 时不应该请求流式接口")

    monkeypatch.setattr(session, "create_completion", fake_completion)
    monkeypatch.setattr(session, "create_stream_completion", fake_stream_completion)
    monkeypatch.setattr(chat_module, "get_client", lambda: SimpleNamespace())

    outputs = [message async for message in session.fetch_llm_response()]

    assert outputs == ["你好"]
    assert session.messages[-1] == {"role": "assistant", "content": "你好"}


async def test_gemini_stream_chunks_drive_chat_stream_sender(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini 转出的分片能被 Chat 的私聊流式发送器直接消费"""
    from nonebot_plugin_chat.core import stream_mode

    payloads: list[dict[str, Any]] = []

    async def fake_request(_bot: Any, _openid: str, payload: dict[str, Any]) -> dict[str, str]:
        payloads.append(payload)
        return {"id": "stream-id"}

    monkeypatch.setattr(stream_mode, "request_stream_message", fake_request)
    monkeypatch.setattr(stream_mode, "MIN_SEND_INTERVAL", 0)

    chat_session = SimpleNamespace(
        session_id="qq_1",
        get_session_type=lambda: "private",
        bot=SimpleNamespace(),
        target=SimpleNamespace(id="openid", private=True, source="msg-id", extra={}),
        format_message=AsyncMock(side_effect=lambda text: SimpleNamespace(extract_plain_text=lambda: text)),
    )
    manager = stream_mode.StreamModeManager(SimpleNamespace(session=chat_session))
    manager._enabled = True
    manager._active = True
    manager._sender_ready = True
    manager._openid = "openid"
    manager._reply_message_id = "msg-id"

    calls: list[str] = []
    _install_client(
        monkeypatch,
        [
            _stream(
                [
                    _chunk(
                        [
                            types.Part(
                                function_call=types.FunctionCall(
                                    id="call-1",
                                    name="send_message",
                                    args={"message_content": "你好"},
                                )
                            )
                        ],
                        types.FinishReason.STOP,
                    )
                ]
            ),
            _stream([_chunk([types.Part(text="好")], types.FinishReason.STOP)]),
        ],
    )
    session = _make_session(_send_message_function(calls), on_stream_chunk=manager.handle_stream_chunk)

    assert [message async for message in session.fetch_llm_response()] == ["好"]
    assert calls == ["你好"]
    # 首片是完整正文，收尾分片把流式消息标记为结束
    assert [payload["content_raw"] for payload in payloads] == ["你好", "你好"]
    assert [payload["input_state"] for payload in payloads] == [1, 10]
    assert await manager.consume_streamed_message("你好") == "stream-id"
