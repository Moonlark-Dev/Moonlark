"""私聊不展示剩余 Token 的回归测试。

Token 池只在群聊中生效：私聊的 additional_info（消息与事件）和 ``send_message``
的工具结果都不应出现「当前 Token / Token 剩余」，群聊行为保持不变。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest


class _FakeTextSession:
    """只实现 additional_info / 发送结果所需的 ``text`` 与 ``get_session_type``"""

    def __init__(self, session_type: str) -> None:
        self._session_type = session_type
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def get_session_type(self) -> str:
        return self._session_type

    async def text(self, key: str, *args: Any) -> str:
        self.calls.append((key, args))
        if key == "prompt_group.state":
            return "状态占位"
        if key.startswith("status.mood."):
            return "开心"
        if key == "message.token":
            return "\nToken 剩余: 3.5 (-1)"
        if key in {"prompt.event_additional_info", "prompt.event_additional_info_private"}:
            return f"{key}:{args!r}"
        if key == "message.sent":
            return "sent:" + "|".join(str(arg) for arg in args)
        return key


def _fake_status_manager() -> SimpleNamespace:
    return SimpleNamespace(
        get_status=lambda: (SimpleNamespace(value="happy"), "因为天气好"),
        get_mood_retention=lambda: 80,
    )


def _make_processor(session_type: str) -> Any:
    import nonebot_plugin_chat.core.processor as processor_module

    processor = processor_module.MessageProcessor.__new__(processor_module.MessageProcessor)
    processor.session = _FakeTextSession(session_type)
    processor.token_bucket = SimpleNamespace(get=lambda: 3.5)
    processor.consecutive_message_count = 1
    processor.pending_notes = {}
    processor._shown_pending_note_ids = set()  # ruff: ignore[private-member-access]
    processor._deliver_message = AsyncMock(return_value="msg-1")  # ruff: ignore[private-member-access]
    return processor


async def _patch_event_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    import nonebot_plugin_chat.core.processor as processor_module
    from nonebot_plugin_chat.core.ego import moonlark_main

    monkeypatch.setattr(processor_module, "get_status_manager", _fake_status_manager)
    monkeypatch.setattr(moonlark_main.sleep_controller, "tiredness", 0.25)


@pytest.mark.asyncio
async def test_private_event_additional_info_omits_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """私聊事件 additional_info 只保留状态与困倦度，不展示剩余 Token"""
    await _patch_event_dependencies(monkeypatch)
    processor = _make_processor("private")

    text = await processor.generate_event_additional_info()

    assert "prompt.event_additional_info_private" in text
    assert "Token" not in text
    assert "prompt.event_additional_info" not in [key for key, _ in processor.session.calls]


@pytest.mark.asyncio
async def test_group_event_additional_info_still_shows_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """群聊事件 additional_info 维持原样，仍包含剩余 Token"""
    await _patch_event_dependencies(monkeypatch)
    processor = _make_processor("group")

    text = await processor.generate_event_additional_info()

    assert "prompt.event_additional_info:" in text
    assert "3.5" in text
    assert "prompt.event_additional_info_private" not in [key for key, _ in processor.session.calls]


@pytest.mark.asyncio
async def test_private_send_message_result_omits_token() -> None:
    """私聊 send_message 的工具结果不附带「Token 剩余」"""
    processor = _make_processor("private")

    result = await processor._send_and_report("你好喵～", None, 0)  # ruff: ignore[private-member-access]

    assert "Token" not in result
    assert "message.token" not in [key for key, _ in processor.session.calls]


@pytest.mark.asyncio
async def test_group_send_message_result_still_shows_token() -> None:
    """群聊 send_message 的工具结果维持原样，仍附带「Token 剩余」"""
    processor = _make_processor("group")

    result = await processor._send_and_report("你好喵～", None, 1)  # ruff: ignore[private-member-access]

    assert "Token 剩余: 3.5 (-1)" in result
    assert "message.token" in [key for key, _ in processor.session.calls]


async def _render_chat_message(**overrides: Any) -> str:
    from nonebot_plugin_openai.utils.message import get_message_text

    kwargs: dict[str, Any] = {
        "current_time": "2026-01-01 00:00:00",
        "token": None,
        "nickname": "小明",
        "display_fav": 10,
        "fav_level": 2,
        "note_text": "暂无",
        "tiredness": 5,
        "state": "状态占位",
        "pending_notes": None,
        "fake_rich_text": None,
        "sender_is_bot": False,
    }
    kwargs.update(overrides)
    return await get_message_text("chat_message.md.jinja", **kwargs)


@pytest.mark.asyncio
async def test_private_message_additional_info_omits_token() -> None:
    """私聊消息 additional_info（token 为 None）不展示当前 Token"""
    text = await _render_chat_message()

    assert "当前 Token" not in text


@pytest.mark.asyncio
async def test_group_message_additional_info_still_shows_token() -> None:
    """群聊消息 additional_info 维持原样，仍展示当前 Token"""
    text = await _render_chat_message(token=3.5)

    assert "当前 Token: 3.5" in text
