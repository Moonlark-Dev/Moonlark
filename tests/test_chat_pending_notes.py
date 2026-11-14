"""待定笔记生成时机测试

待定笔记不再按消息条数单独触发：EventCollector 在事件总结成功后把同一个 block
的聊天记录传给 ``MessageProcessor.analyze_pending_notes``，两者针对同一批消息一起生成。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from unittest.mock import AsyncMock, patch


def _fake_processor(get_cached_messages_string: AsyncMock | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        _pending_note_lock=asyncio.Lock(),
        _next_pending_note_id=0,
        pending_notes={},
        session=SimpleNamespace(
            session_id="pytest_pending_notes_group",
            get_cached_messages_string=get_cached_messages_string or AsyncMock(return_value="不应被调用"),
        ),
    )


def _fake_note_manager() -> SimpleNamespace:
    return SimpleNamespace(get_notes=AsyncMock(return_value=[]))


async def test_analyze_pending_notes_uses_provided_block_history() -> None:
    """传入 block 聊天记录时不再另外读取缓存消息"""
    import importlib

    processor_module = importlib.import_module("nonebot_plugin_chat.core.processor")
    get_cached_messages_string = AsyncMock(return_value="旧的缓存消息")
    processor = _fake_processor(get_cached_messages_string)

    with (
        patch.object(processor_module, "get_message_text", AsyncMock(return_value="提示词")),
        patch.object(processor_module, "generate_message", lambda text, role: {"role": role, "content": text}),
        patch.object(
            processor_module,
            "fetch_message",
            AsyncMock(return_value='[{"content": "小明喜欢排球", "keywords": "小明 排球", "expire_hours": 720}]'),
        ),
        patch.object(processor_module, "get_context_notes", AsyncMock(return_value=_fake_note_manager())),
    ):
        await processor_module.MessageProcessor.analyze_pending_notes(processor, "[10:00:00][小明]: 我喜欢排球")

    get_cached_messages_string.assert_not_awaited()
    assert processor.pending_notes[0]["content"] == "小明喜欢排球"
    assert processor.pending_notes[0]["keywords"] == "小明 排球"
    assert processor._next_pending_note_id == 1


async def test_analyze_pending_notes_falls_back_to_cached_messages() -> None:
    """手动场景（未传聊天记录）仍回退到最近 50 条缓存消息"""
    import importlib

    processor_module = importlib.import_module("nonebot_plugin_chat.core.processor")
    get_cached_messages_string = AsyncMock(return_value="[10:00:00][小明]: 我喜欢排球")
    processor = _fake_processor(get_cached_messages_string)

    with (
        patch.object(processor_module, "get_message_text", AsyncMock(return_value="提示词")),
        patch.object(processor_module, "generate_message", lambda text, role: {"role": role, "content": text}),
        patch.object(processor_module, "fetch_message", AsyncMock(return_value="[]")),
        patch.object(processor_module, "get_context_notes", AsyncMock(return_value=_fake_note_manager())),
    ):
        await processor_module.MessageProcessor.analyze_pending_notes(processor)

    get_cached_messages_string.assert_awaited_once()
    assert processor.pending_notes == {}


async def test_analyze_pending_notes_skips_empty_history() -> None:
    """空聊天记录不会发起模型请求"""
    import importlib

    processor_module = importlib.import_module("nonebot_plugin_chat.core.processor")
    processor = _fake_processor()

    with patch.object(processor_module, "fetch_message", AsyncMock()) as fetch:
        await processor_module.MessageProcessor.analyze_pending_notes(processor, "   ")

    fetch.assert_not_awaited()
