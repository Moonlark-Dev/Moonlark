"""at 插话触发回归测试

覆盖三个「@ 插话不触发」的成因：

1. ``MessageQueue.fetch_reply`` 在上一个 LLM 请求进行中时静默丢弃重要回复
   （important 现在应等待锁释放后补发，非 important 保持原样直接跳过）；
2. ``MessageProcessor._check_rules`` 的冷却期（cold_until）拦截 important 插话；
3. ``MessageProcessor.is_additional_info_line_showed`` 持有 fetcher_lock，
   使新消息解析被正在进行的 LLM 请求卡住（现改为无锁快照遍历）。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch


def _make_queue() -> Any:
    """构造一个最小可用的 MessageQueue（不触发真实 LLM 请求）"""
    from nonebot_plugin_chat.core.message import MessageQueue

    session = SimpleNamespace(
        session_id="qq_1",
        get_session_type=lambda: "group",
        processor=SimpleNamespace(),
    )
    return MessageQueue(SimpleNamespace(session=session))


async def _release_lock_later(lock: asyncio.Lock, delay: float = 0.2) -> None:
    await asyncio.sleep(delay)
    lock.release()


async def test_fetch_reply_drops_when_busy_without_wait() -> None:
    """非 important 回复在请求进行中保持原行为：直接跳过，不排队"""
    from nonebot_plugin_chat.enums import FetchStatus

    queue = _make_queue()
    fetch_mock = AsyncMock(return_value=FetchStatus.SUCCESS)
    await queue.fetcher_lock.acquire()  # 模拟上一个请求尚未结束
    try:
        with patch.object(type(queue), "_fetch_reply", fetch_mock):
            await asyncio.wait_for(queue.fetch_reply(), 0.5)
    finally:
        if queue.fetcher_lock.locked():
            queue.fetcher_lock.release()
    fetch_mock.assert_not_awaited()
    assert queue.fetcher_task is None


async def test_fetch_reply_waits_for_running_request_when_important() -> None:
    """important 回复（@ 插话）在请求进行中应等待其结束后补发，而不是被吞掉"""
    from nonebot_plugin_chat.enums import FetchStatus

    queue = _make_queue()
    fetch_mock = AsyncMock(return_value=FetchStatus.SUCCESS)
    await queue.fetcher_lock.acquire()
    release_task = asyncio.create_task(_release_lock_later(queue.fetcher_lock))
    try:
        with patch.object(type(queue), "_fetch_reply", fetch_mock):
            await asyncio.wait_for(queue.fetch_reply(wait_if_busy=True), 5)
    finally:
        if not release_task.done():
            release_task.cancel()
            await asyncio.wait([release_task], timeout=1)
        if queue.fetcher_lock.locked():
            queue.fetcher_lock.release()
    fetch_mock.assert_awaited_once()


async def test_fetch_reply_skips_after_wait_if_already_answered() -> None:
    """等待结束后，若上一个请求已经回复过（最后一条是 assistant），本轮跳过，不会重复回复"""

    queue = _make_queue()
    create_fetcher_mock = AsyncMock(return_value=None)
    await queue.fetcher_lock.acquire()
    release_task = asyncio.create_task(_release_lock_later(queue.fetcher_lock))
    try:
        # 模拟上一个请求已经产出回复：LLM 消息列表以 assistant 结尾
        with patch.object(type(queue), "messages", property(lambda self: [{"role": "assistant", "content": "已回复"}])):
            with patch.object(type(queue), "_create_fetcher", create_fetcher_mock):
                await asyncio.wait_for(queue.fetch_reply(wait_if_busy=True), 5)
    finally:
        if not release_task.done():
            release_task.cancel()
            await asyncio.wait([release_task], timeout=1)
        if queue.fetcher_lock.locked():
            queue.fetcher_lock.release()
    # 最后一条消息来自 assistant：_fetch_reply 应直接 SKIP，从未创建请求
    create_fetcher_mock.assert_not_awaited()
    assert queue.fetcher is None


def _make_rules_self() -> SimpleNamespace:
    """构造 _check_rules 需要的最小 self（消息数 ≥ 5 避开 min_messages 检查）"""
    openai_messages = SimpleNamespace(
        messages=[{"role": "user", "content": "hi"}] * 5,
        is_last_message_from_user=lambda: True,
    )
    return SimpleNamespace(
        cold_until=datetime.now() + timedelta(seconds=3),
        openai_messages=openai_messages,
    )


async def test_check_rules_cold_period_allows_important() -> None:
    """冷却期不拦截 @ 插话（important），非 important 仍被拦截"""
    from nonebot_plugin_chat.core.processor import MessageProcessor

    fake_self = _make_rules_self()
    assert await MessageProcessor._check_rules(fake_self, True, True, 0) is True
    assert await MessageProcessor._check_rules(fake_self, False, True, 0) is False


async def test_check_rules_cold_period_blocks_normal() -> None:
    """冷却期结束后非 important 回复可以正常通过规则检查"""
    from nonebot_plugin_chat.core.processor import MessageProcessor

    fake_self = _make_rules_self()
    assert await MessageProcessor._check_rules(fake_self, False, True, 0) is False
    fake_self.cold_until = datetime.now() - timedelta(seconds=1)
    assert await MessageProcessor._check_rules(fake_self, False, True, 0) is True


async def test_check_additional_info_line_while_fetch_in_progress() -> None:
    """解析路径不持有 fetcher_lock：LLM 请求进行中消息解析仍能立即完成"""
    from nonebot_plugin_chat.core.processor import MessageProcessor

    lock = asyncio.Lock()
    openai_messages = SimpleNamespace(
        fetcher_lock=lock,  # 保留锁字段模拟真实对象；修复后解析路径不应再获取它
        messages=[{"role": "user", "content": "[10:00:00] 备注: 别忘了带伞"}],
    )
    fake_self = SimpleNamespace(openai_messages=openai_messages, _normalize_line=lambda text: text)

    await lock.acquire()
    release_task = asyncio.create_task(_release_lock_later(lock, delay=2))
    try:
        # 修复前这里会阻塞到锁释放；修复后应立即返回
        showed = await asyncio.wait_for(
            MessageProcessor.is_additional_info_line_showed(fake_self, "[10:00:00] 备注: 别忘了带伞"), 1
        )
    finally:
        if not release_task.done():
            release_task.cancel()
            await asyncio.wait([release_task], timeout=1)
        if lock.locked():
            lock.release()
    assert showed is True

    not_showed = await asyncio.wait_for(
        MessageProcessor.is_additional_info_line_showed(fake_self, "[10:00:00] 其他内容"), 1
    )
    assert not_showed is False
