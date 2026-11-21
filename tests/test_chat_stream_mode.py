"""私聊流式发送的回归测试

覆盖流式工具参数的分片解析、QQ 流式消息发送分片、``/chat stream`` 指令与
``gal-mode`` 的互斥，以及 ``nonebot_plugin_openai`` 的流式请求路径。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest


def test_extract_partial_json_string_handles_incomplete_json() -> None:
    """工具参数还没收尾时也要能解析出正文前缀"""
    from nonebot_plugin_chat.core.stream_mode import extract_partial_json_string

    assert extract_partial_json_string('{"message_content": "你好') == "你好"
    assert extract_partial_json_string('{"message_content": "你好"') == "你好"
    assert extract_partial_json_string('{"message_content": "你好", "reply_message_id": "x"}') == "你好"
    assert extract_partial_json_string('{"message_content": "abc\\') == "abc"
    assert extract_partial_json_string('{"message_content": "abc\\u12') == "abc"
    assert extract_partial_json_string('{"reply_message_id": "x"}') is None
    assert extract_partial_json_string('{"message_content": 1}') is None


def test_extract_partial_json_string_decodes_escapes() -> None:
    """引号、换行、Unicode 转义按 JSON 规则还原"""
    from nonebot_plugin_chat.core.stream_mode import extract_partial_json_string

    assert extract_partial_json_string('{"message_content": "a\\"b\\n\\u4f60"}') == 'a"b\n你'
    assert extract_partial_json_string('{"message_content": "\\ud83d\\ude00"}') == "\ud83d\ude00"


async def test_qq_stream_sender_payloads() -> None:
    """首片不带 stream_msg_id，后续分片沿用首片返回的 ID"""
    from nonebot.drivers import URL

    from nonebot_plugin_chat.core import stream_mode

    requests: list[Any] = []

    class FakeAdapter:
        @staticmethod
        def get_api_base() -> URL:
            return URL("https://example.com")

    class FakeBot:
        adapter = FakeAdapter()

        @staticmethod
        async def _request(request: Any) -> dict[str, str]:
            requests.append(request)
            return {"id": "stream-id"}

    sender = stream_mode.QQStreamMessageSender(FakeBot(), "openid", "msg-id", 42)

    assert await sender.send("你") == "stream-id"
    assert await sender.send("你好", final=True) == "stream-id"

    first, second = (request.json for request in requests)
    assert first["index"] == 0
    assert first["input_state"] == 1
    assert first["content_raw"] == "你"
    assert first["msg_id"] == "msg-id"
    assert first["msg_seq"] == 42
    assert "stream_msg_id" not in first
    assert second["index"] == 1
    assert second["input_state"] == 10
    assert second["content_raw"] == "你好"
    assert second["stream_msg_id"] == "stream-id"
    assert str(requests[0].url).endswith("/v2/users/openid/stream_messages")


def _make_stream_manager() -> tuple[Any, Any]:
    """构造一个最小可用的 StreamModeManager（直接进入可分片状态）"""
    from nonebot_plugin_chat.core.stream_mode import StreamModeManager

    session = SimpleNamespace(
        session_id="qq_1",
        get_session_type=lambda: "private",
        bot=SimpleNamespace(),
        target=SimpleNamespace(id="openid", private=True, source="msg-id", extra={}),
        format_message=AsyncMock(side_effect=lambda text: SimpleNamespace(extract_plain_text=lambda: text)),
    )
    processor = SimpleNamespace(session=session)
    manager = StreamModeManager(processor)
    manager._enabled = True
    manager._active = True
    manager._sender_ready = True
    manager._openid = "openid"
    manager._reply_message_id = "msg-id"
    return manager, processor


def _tool_call_chunk(arguments: str, *, finish: str | None = None) -> Any:
    delta = SimpleNamespace(
        content=None,
        tool_calls=[
            SimpleNamespace(
                index=0,
                id="call-1",
                function=SimpleNamespace(name="send_message", arguments=arguments),
            )
        ],
    )
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish)])


async def test_stream_manager_sends_fragments_and_finalizes(monkeypatch: pytest.MonkeyPatch) -> None:
    """流式分片按节流发送，finish_reason 时收尾，工具执行时能匹配到已发消息"""
    from nonebot_plugin_chat.core import stream_mode

    payloads: list[dict[str, Any]] = []

    async def fake_request(_bot: Any, _openid: str, payload: dict[str, Any]) -> dict[str, str]:
        payloads.append(payload)
        return {"id": "stream-id"}

    monkeypatch.setattr(stream_mode, "request_stream_message", fake_request)
    monkeypatch.setattr(stream_mode, "MIN_SEND_INTERVAL", 0)
    manager, _ = _make_stream_manager()

    await manager.handle_stream_chunk(_tool_call_chunk('{"message_content": "你'))
    await manager.handle_stream_chunk(_tool_call_chunk('好"}'))
    await manager.handle_stream_chunk(
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(), finish_reason="tool_calls")])
    )

    assert [payload["content_raw"] for payload in payloads] == ["你", "你好", "你好"]
    assert [payload["input_state"] for payload in payloads] == [1, 1, 10]
    assert await manager.consume_streamed_message("你好") == "stream-id"
    assert await manager.consume_streamed_message("你好") is None


async def test_stream_manager_does_not_send_when_not_qq() -> None:
    """没有 QQ 流式发送目标时只切换请求模式，不影响普通发送"""
    from nonebot_plugin_chat.core.stream_mode import StreamModeManager

    session = SimpleNamespace(
        session_id="qq_1",
        get_session_type=lambda: "private",
        bot=SimpleNamespace(),
        target=SimpleNamespace(id="openid", private=True, source="", extra={}),
    )
    manager = StreamModeManager(SimpleNamespace(session=session))
    manager._enabled = True
    manager._active = True
    manager._sender_ready = False

    await manager.handle_stream_chunk(_tool_call_chunk('{"message_content": "你"}'))

    assert manager.should_stream()
    assert await manager.consume_streamed_message("你") is None


async def test_send_message_skips_delivery_for_streamed_content() -> None:
    """正文已经流式发出时，send_message 只补记上下文，不再调用平台发送"""
    from nonebot_plugin_chat.core.processor import MessageProcessor

    processor = SimpleNamespace(
        stream_mode=SimpleNamespace(consume_streamed_message=AsyncMock(return_value="stream-id")),
        gal_mode=SimpleNamespace(should_buffer=lambda: False),
        session=SimpleNamespace(
            get_session_type=lambda: "private",
            text=AsyncMock(return_value="消息已通过流式发送。"),
            last_activate=None,
        ),
        consecutive_message_count=0,
        _record_sent_message=AsyncMock(),
        _record_reply_timing=lambda *_, **__: None,
    )

    result = await MessageProcessor.send_message(processor, "你好")

    assert result == "消息已通过流式发送。"
    processor.stream_mode.consume_streamed_message.assert_awaited_once_with("你好")
    processor._record_sent_message.assert_awaited_once_with("你好", "stream-id")


def _make_send_processor(*, streaming: bool) -> SimpleNamespace:
    """构造一个只走到普通发送分支的 processor，用于检查 reply_message_id 的去留"""
    return SimpleNamespace(
        stream_mode=SimpleNamespace(
            consume_streamed_message=AsyncMock(return_value=None),
            streaming=streaming,
        ),
        gal_mode=SimpleNamespace(should_buffer=lambda: False),
        session=SimpleNamespace(
            get_session_type=lambda: "private",
            text=AsyncMock(return_value="ok"),
            last_activate=None,
        ),
        consecutive_message_count=0,
        _record_sent_message=AsyncMock(),
        _record_reply_timing=lambda *_, **__: None,
        _send_and_report=AsyncMock(return_value="ok"),
    )


async def test_send_message_drops_reply_message_id_while_streaming() -> None:
    """正文会走流式消息时，普通发送不再带 reply_message_id，避免同一条内容出现两条消息"""
    from nonebot_plugin_chat.core.processor import MessageProcessor

    processor = _make_send_processor(streaming=True)

    await MessageProcessor.send_message(processor, "你好", "msg-1")

    processor._send_and_report.assert_awaited_once_with("你好", None, 0, enhanced=False)


async def test_send_message_keeps_reply_message_id_when_not_streaming() -> None:
    """正文不会走流式消息（开关关闭 / Gemini / 非 QQ 官方私聊）时照常引用"""
    from nonebot_plugin_chat.core.processor import MessageProcessor

    processor = _make_send_processor(streaming=False)

    await MessageProcessor.send_message(processor, "你好", "msg-1")

    processor._send_and_report.assert_awaited_once_with("你好", "msg-1", 0, enhanced=False)


async def test_stream_manager_streaming_requires_supported_provider_and_platform() -> None:
    """只有「开关打开 + QQ 官方私聊 + Provider 支持流式」才算正文会走流式消息"""
    from nonebot_plugin_chat.core.stream_mode import StreamModeManager

    manager = StreamModeManager(SimpleNamespace(session=SimpleNamespace()))
    manager._enabled = True
    manager._sender_ready = True

    manager._provider = "openai"
    assert manager.streaming

    manager._provider = "gemini"
    assert not manager.streaming

    manager._provider = "openai"
    manager._sender_ready = False
    assert not manager.streaming

    manager._sender_ready = True
    manager._enabled = False
    assert not manager.streaming


async def test_chat_stream_command_toggles_and_disables_gal_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """``/chat stream on`` 写入 stream 并关闭 gal_mode，反之只写 stream"""
    from nonebot_plugin_chat.matcher import chat as module

    class _Stop(Exception):
        pass

    finished: list[str] = []

    async def fake_finish(key: str, user_id: str, *args: Any) -> None:
        finished.append(key)
        raise _Stop

    monkeypatch.setattr(module.lang, "finish", fake_finish)

    def make_handler(config: Any, argv: list[str]) -> Any:
        handler = module.CommandHandler(
            mathcer=SimpleNamespace(),
            bot=SimpleNamespace(),
            session=SimpleNamespace(merge=AsyncMock(), commit=AsyncMock()),
            message=SimpleNamespace(extract_plain_text=lambda: ""),
            event=SimpleNamespace(),
            group_id="qq_1",
            user_id="123",
        )
        handler.is_private_chat = True
        handler.private_config = config
        handler.argv = argv
        return handler

    handler = make_handler(SimpleNamespace(enabled=True, stream=False, gal_mode=True), ["stream", "on"])
    with pytest.raises(_Stop):
        await handler.handle_stream()
    config = handler.session.merge.await_args.args[0]
    assert config.stream is True
    assert config.gal_mode is False
    assert finished == ["command.stream.enabled_gal_disabled"]

    finished.clear()
    handler = make_handler(SimpleNamespace(enabled=True, stream=True, gal_mode=False), ["stream", "off"])
    with pytest.raises(_Stop):
        await handler.handle_stream()
    assert handler.private_config.stream is False
    assert handler.private_config.gal_mode is False
    assert finished == ["command.stream.disabled"]


async def test_chat_stream_command_shows_default_on_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有配置记录时展示默认开启状态，不写库"""
    from nonebot_plugin_chat.matcher import chat as module

    class _Stop(Exception):
        pass

    finished: list[str] = []

    async def fake_finish(key: str, user_id: str, *args: Any) -> None:
        finished.append(key)
        raise _Stop

    monkeypatch.setattr(module.lang, "finish", fake_finish)
    handler = module.CommandHandler(
        mathcer=SimpleNamespace(),
        bot=SimpleNamespace(),
        session=SimpleNamespace(merge=AsyncMock(), commit=AsyncMock()),
        message=SimpleNamespace(extract_plain_text=lambda: ""),
        event=SimpleNamespace(),
        group_id="qq_1",
        user_id="123",
    )
    handler.is_private_chat = True
    handler.private_config = None
    handler.argv = ["stream"]

    with pytest.raises(_Stop):
        await handler.handle_stream()

    assert finished == ["command.stream.current_on"]
    handler.session.merge.assert_not_awaited()


async def test_gal_mode_enable_disables_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """``/gal-mode on`` 与流式发送互斥：会关闭 stream 并提示"""
    from nonebot_plugin_chat.matcher import gal_mode as module

    class _Stop(Exception):
        pass

    finished: list[str] = []

    async def fake_finish(key: str, user_id: str, *args: Any) -> None:
        finished.append(key)
        raise _Stop

    monkeypatch.setattr(module, "private_message", AsyncMock(return_value=True))
    monkeypatch.setattr(module.lang, "finish", fake_finish)
    existing = SimpleNamespace(enabled=True, gal_mode=False, stream=True)
    session = SimpleNamespace(get=AsyncMock(return_value=existing), merge=AsyncMock(), commit=AsyncMock())

    with pytest.raises(_Stop):
        await module._(
            event=SimpleNamespace(),
            session=session,
            message=SimpleNamespace(extract_plain_text=lambda: "on"),
            user_id="123",
        )

    assert existing.gal_mode is True
    assert existing.stream is False
    assert finished == ["command.gal_mode.enabled_stream_disabled"]


async def test_openai_stream_accumulates_content_and_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """流式请求逐片产出正文，结束后执行 send_message 工具调用"""
    from nonebot_plugin_openai import generate_message
    from nonebot_plugin_openai.utils import chat as chat_module

    calls: list[dict[str, Any]] = []

    async def send_message(message_content: str) -> str:
        calls.append({"message_content": message_content})
        return "工具结果"

    function = {
        "func": send_message,
        "description": "发送消息",
        "parameters": {
            "message_content": {"type": "string", "description": "消息内容", "required": True},
        },
    }

    class FakeStream:
        def __init__(self, chunks: list[Any]) -> None:
            self._chunks = iter(chunks)

        def __aiter__(self) -> "FakeStream":
            return self

        async def __anext__(self) -> Any:
            try:
                return next(self._chunks)
            except StopIteration:
                raise StopAsyncIteration

    first_stream = FakeStream(
        [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="你", tool_calls=None), finish_reason=None)]
            ),
            _tool_call_chunk('{"message_content": "你好"}', finish="tool_calls"),
        ]
    )
    second_stream = FakeStream(
        [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="好", tool_calls=None), finish_reason="stop")]
            )
        ]
    )
    streams = iter([first_stream, second_stream])

    class FakeCompletions:
        @staticmethod
        async def create(**kwargs: Any) -> FakeStream:
            assert kwargs["stream"] is True
            return next(streams)

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(chat_module, "client", FakeClient())
    chunks: list[Any] = []
    session = chat_module.LLMRequestSession(
        [generate_message("hi", "user")],
        {"send_message": function},
        "test-model",
        {},
        "Test",
        stream=True,
        on_stream_chunk=AsyncMock(side_effect=chunks.append),
    )

    outputs = [message async for message in session.fetch_llm_response()]

    assert outputs == ["你", "好"]
    assert calls == [{"message_content": "你好"}]
    assert len(chunks) == 3
    # 工具调用与工具返回按 OpenAI 消息格式写回消息列表
    assert session.messages[1]["role"] == "assistant"
    assert session.messages[1]["tool_calls"][0]["function"]["name"] == "send_message"
    assert session.messages[2]["role"] == "tool"
    assert session.messages[3]["content"] == "好"
