"""会话创建与上下文启动的失败处理

覆盖两类曾经会静默吞掉整条消息通路的问题：

- ``setup()`` 失败（例如工具定义文件缺失）后，半初始化的会话仍留在 ``groups``
  里，后续消息只会堆在队列上，chat monitor 一直显示「解析中」，也不会有回复；
- 上下文恢复任务 ``_startup`` 失败后没有人重试，消息同样永远留在队列里。
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


class _FakeSession:
    """MessageProcessor 需要的最小会话"""

    lang_str = "zh_hans"
    session_id = "qq_test"

    def __init__(self) -> None:
        from nonebot_plugin_chat.core.session.base import SessionQueue

        self.processor: Any = None
        self.message_queue = SessionQueue(self._on_item_queued)

    def _on_item_queued(self) -> None:
        if self.processor is not None:
            self.processor.notify_message_queued()

    def is_napcat_bot(self) -> bool:
        return False


async def test_failed_context_startup_is_retried_on_next_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """上下文恢复失败后，下一条消息要能重新拉起启动任务并消费队列"""
    from nonebot_plugin_chat.core.processor import MessageProcessor

    session = _FakeSession()
    processor = MessageProcessor(session)  # type: ignore[arg-type]
    session.processor = processor

    start = AsyncMock(side_effect=RuntimeError("恢复失败"))
    monkeypatch.setattr(processor.openai_messages, "start", start)

    async def fake_get_message() -> None:
        session.message_queue.pop(0)

    monkeypatch.setattr(processor, "get_message", fake_get_message)

    # 恢复一直失败时消息只能留在队列里（没有上下文可用）
    processor.ensure_startup()
    session.message_queue.append(("message", ("m1",)))
    await asyncio.sleep(0.05)
    assert len(session.message_queue) == 1

    # 恢复成功后的下一条消息必须把队列整个消费掉
    start.side_effect = None
    start.return_value = None
    session.message_queue.append(("message", ("m2",)))
    for _ in range(50):
        if not session.message_queue:
            break
        await asyncio.sleep(0.01)

    assert not session.message_queue, "重试成功后队列仍未被消费"


async def test_failed_setup_does_not_leave_zombie_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """setup() 失败时不能把半初始化的会话留在 groups 里"""
    from nonebot_plugin_chat.core import session as session_module
    from nonebot_plugin_chat.core.session.group import GroupSession

    class BrokenSession(GroupSession):
        async def setup(self) -> None:
            raise FileNotFoundError("工具定义文件缺失")

    monkeypatch.setattr(session_module, "GroupSession", BrokenSession)
    monkeypatch.setattr(session_module, "get_group_language", AsyncMock(return_value="zh_hans"))
    session_module.groups.clear()

    with pytest.raises(FileNotFoundError):
        await session_module.create_group_session("qq_10000", MagicMock(), MagicMock())

    assert "qq_10000" not in session_module.groups, "初始化失败的会话仍留在 groups 里"


async def test_setup_failure_keeps_existing_session_untouched() -> None:
    """已存在（且初始化成功）的会话不受后续创建失败的影响"""
    from nonebot_plugin_chat.core import session as session_module

    existing = MagicMock()
    session_module.groups.clear()
    session_module.groups["qq_10000"] = existing

    assert await session_module.create_group_session("qq_10000", MagicMock(), MagicMock()) is existing
