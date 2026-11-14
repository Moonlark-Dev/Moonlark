"""请求体 NUL 清理测试

网关（AxonHub 等）会把请求体原样写进 PostgreSQL 的 ``jsonb`` 列，而 ``jsonb`` 拒收
JSON 里的 ``\\u0000``：请求体里只要混进一个 NUL，整次请求的请求体就会落库失败，网关
用 ``{"message": "invalid text"}`` 占位，从外部看起来就像 Moonlark 发了一条空请求。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest


def test_strip_nul_removes_nul_from_nested_payloads() -> None:
    from nonebot_plugin_openai.utils.sanitize import strip_nul

    payload = {
        "role": "user",
        "content": [
            {"type": "text", "text": "你好\x00世界"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        ],
        "tool_calls": [{"id": "call\x00_1", "function": {"arguments": '{"q": "x\\u0000y"}'}}],
        "count": 1,
        "flags": [True, None],
    }

    cleaned = strip_nul(payload)

    assert "\x00" not in json.dumps(cleaned, ensure_ascii=False)
    assert cleaned["content"][0]["text"] == "你好世界"
    assert cleaned["tool_calls"][0]["id"] == "call_1"
    # 只清理真正的 NUL，字面量 \u0000 是普通文本，不能被误删
    assert cleaned["tool_calls"][0]["function"]["arguments"] == '{"q": "x\\u0000y"}'
    # 入参本身不被改写
    assert payload["content"][0]["text"] == "你好\x00世界"


def test_strip_nul_serializes_pydantic_messages() -> None:
    from openai.types.chat import ChatCompletionMessage

    from nonebot_plugin_openai.utils.sanitize import strip_nul

    cleaned = strip_nul([ChatCompletionMessage(role="assistant", content="回\x00复")])

    assert isinstance(cleaned[0], dict)
    assert cleaned[0]["content"] == "回复"


async def test_create_completion_strips_nul_from_outgoing_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_openai.utils import chat as chat_module

    captured: dict[str, Any] = {}

    async def _fake_create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return SimpleNamespace(choices=[])

    session = chat_module.LLMRequestSession(
        messages=[{"role": "user", "content": "你好\x00世界"}],
        func_index={},
        model="test-model",
        kwargs={},
        identify="Chat",
    )
    session.func_list = [
        {"type": "function", "function": {"name": "search", "description": "搜\x00索", "parameters": {}}},
    ]
    monkeypatch.setattr(chat_module.client.chat.completions, "create", _fake_create)

    await session.create_completion()

    assert "\x00" not in json.dumps(captured["messages"], ensure_ascii=False)
    assert "\x00" not in json.dumps(captured["tools"], ensure_ascii=False)
    assert captured["messages"][0]["content"] == "你好世界"
    # 原消息列表必须保持原样：chat context 靠它与请求列表做前缀对齐
    assert session.messages[0]["content"] == "你好\x00世界"


async def test_call_function_strips_nul_from_tool_result() -> None:
    from nonebot_plugin_openai.utils.chat import LLMRequestSession

    async def _command_output() -> str:
        return "日志\x00输出"

    session = LLMRequestSession(
        messages=[],
        func_index={"run_command": {"func": _command_output, "description": "", "parameters": {}}},
        model="test-model",
        kwargs={},
        identify="Chat",
    )

    await session.call_function("call_1", "run_command", {})

    assert session.messages[-1]["content"] == "日志输出"


def test_build_message_content_strips_nul_from_message_text() -> None:
    from nonebot_plugin_chat.core.processor import MessageProcessor

    processor = MessageProcessor.__new__(MessageProcessor)

    content = processor.build_message_content("[小明](123): 你好\x00世界", [])

    assert content[0]["text"] == "[小明](123): 你好世界"


async def test_generate_image_strips_nul_from_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_openai.utils import image_generation

    captured: dict[str, Any] = {}

    async def _fake_generate(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return SimpleNamespace(data=[])

    monkeypatch.setattr(image_generation, "get_model_for_identify", AsyncMock(return_value="test-model"))
    monkeypatch.setattr(image_generation.client.images, "generate", _fake_generate)

    with pytest.raises(Exception, match="空数据"):
        await image_generation.generate_image("画\x00一只猫")

    assert captured["prompt"] == "画一只猫"


def test_strip_tool_call_extras_removes_gemini_fields() -> None:
    """Gemini 模式下 tool_calls 里会带上 thought_signature 等字段，发给 OpenAI 前要剔除"""
    from nonebot_plugin_gemini.utils.convert import THOUGHT_SIGNATURE_KEY
    from nonebot_plugin_openai.utils.sanitize import strip_tool_call_extras

    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "f", "arguments": "{}", "extra": "x"},
                    THOUGHT_SIGNATURE_KEY: "c2lnbmF0dXJl",
                }
            ],
        },
        {"role": "user", "content": "hi"},
    ]

    cleaned = strip_tool_call_extras(messages)

    assert cleaned[0]["tool_calls"] == [
        {"id": "call-1", "type": "function", "function": {"name": "f", "arguments": "{}"}}
    ]
    # 入参不被改写（chat context 依靠它与请求列表一致做前缀对齐）
    assert THOUGHT_SIGNATURE_KEY in messages[0]["tool_calls"][0]


def test_strip_tool_call_extras_keeps_messages_without_tool_calls() -> None:
    from nonebot_plugin_openai.utils.sanitize import strip_tool_call_extras

    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "在", "tool_calls": None},
    ]

    assert strip_tool_call_extras(messages) == messages
