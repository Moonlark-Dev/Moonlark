"""Chat Context 在 Gemini 模式下的两处差异：内容替换与更短的 block 选择等待时间"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Optional
from unittest.mock import AsyncMock

import pytest


class _FakeMessage:
    def __init__(
        self,
        role: str,
        content: Any,
        *,
        block_id: int = 1,
        request_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        self.role = role
        self.content = content
        self.sub_type = ""
        self.block_id = block_id
        self.request_id = request_id
        self.timestamp = timestamp or datetime.now()
        self.in_llm_context = True
        self.display_only = False
        self.invalidations = 0

    def invalidate_signature(self) -> None:
        self.invalidations += 1

    def signature(self) -> str:
        return json.dumps({"role": self.role, "content": self.content}, ensure_ascii=False)


def _make_context(messages: list[_FakeMessage]) -> Any:
    from nonebot_plugin_chat.core.context import ChatContext

    session = type("Session", (), {"session_id": "qq_1", "lang_str": "zh_hans"})()
    context = ChatContext(session)
    context._messages = messages  # type: ignore[assignment]
    return context


async def test_replace_llm_message_content() -> None:
    """替换 LLM 消息内容：更新 content、让指纹失效并重新排队落库"""
    messages = [
        _FakeMessage("system", "系统"),
        _FakeMessage("user", [{"type": "text", "text": "看图"}, {"type": "image_url", "image_url": {}}]),
    ]
    context = _make_context(messages)
    new_content = [{"type": "text", "text": "看图"}, {"type": "text", "text": "[图片(img_1): 一只猫]"}]

    assert await context.replace_llm_message_content(1, new_content) is True
    assert messages[1].content == new_content
    assert messages[1].invalidations == 1
    assert messages[1] in context._pending


async def test_replace_llm_message_content_out_of_range() -> None:
    """下标越界时不修改任何消息"""
    messages = [_FakeMessage("user", "hi")]
    context = _make_context(messages)

    assert await context.replace_llm_message_content(5, "other") is False
    assert messages[0].content == "hi"
    assert context._pending == []


async def test_replace_llm_message_content_is_idempotent() -> None:
    """内容没有变化时不做无谓的失效与落库"""
    message = _FakeMessage("user", "hi")
    context = _make_context([message])

    assert await context.replace_llm_message_content(0, "hi") is True
    assert message.invalidations == 0
    assert context._pending == []


@pytest.mark.parametrize(("idle_seconds", "expected"), [(300, True), (600, False)])
async def test_run_sliding_window_respects_idle_seconds(
    monkeypatch: pytest.MonkeyPatch, idle_seconds: float, expected: bool
) -> None:
    """``run_sliding_window`` 按调用方给出的等待时长决定是否执行 block 选择"""
    now = datetime.now()
    messages = [
        _FakeMessage("user", "旧消息", block_id=1, timestamp=now - timedelta(minutes=20)),
        _FakeMessage("assistant", "回复", block_id=1, request_id="req-1", timestamp=now - timedelta(minutes=8)),
        _FakeMessage("user", "新消息", block_id=2, timestamp=now - timedelta(minutes=1)),
    ]
    context = _make_context(messages)

    async def fake_events(_block_id: int) -> str:
        return "事件"

    async def fake_relevant(_history: str, _latest: str) -> bool:
        return False

    truncate = AsyncMock()
    monkeypatch.setattr(context, "_get_block_events_text", fake_events)
    monkeypatch.setattr(context, "_block_still_relevant", fake_relevant)
    monkeypatch.setattr(context, "_truncate_from_block", truncate)

    assert await context.run_sliding_window(idle_seconds) is expected
    if expected:
        truncate.assert_awaited_once_with(1)
    else:
        truncate.assert_not_awaited()
