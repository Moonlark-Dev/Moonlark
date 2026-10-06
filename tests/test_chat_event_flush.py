"""事件收集器积压消息收集测试：planner 与主动私聊决策前必须先补齐会话事件

block 化之后，积压量来自 chat context 当前 block 中尚未提交事件总结的消息数
（``pending_block_message_count``），以及此前总结失败、等待重试的 block。
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch


def _event_collector_singleton():
    module = importlib.import_module("nonebot_plugin_chat.core.ego.event_collector")
    return module, module.event_collector


def _fake_context(pending: int, unsummarized: list[int] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        pending_block_message_count=pending,
        unsummarized_blocks=list(unsummarized or []),
        current_block_id=1,
        freeze_block=lambda block_id: True,
    )


def _fake_session(session_id: str, pending: int, unsummarized: list[int] | None = None) -> Any:
    return SimpleNamespace(
        session_id=session_id,
        processor=SimpleNamespace(openai_messages=SimpleNamespace(context=_fake_context(pending, unsummarized))),
    )


async def test_flush_pending_skips_sessions_at_or_below_threshold() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector

    session_module = importlib.import_module("nonebot_plugin_chat.core.session")
    collector = EventCollector()
    groups = {
        "s1": _fake_session("s1", 6),
        "s2": _fake_session("s2", 5),
        "s3": _fake_session("s3", 0),
        "s4": _fake_session("s4", 100),
    }

    collect = AsyncMock()
    with (
        patch.object(collector, "_collect", collect),
        patch.object(session_module, "groups", groups),
    ):
        flushed = await collector.flush_pending()

    # 只有「消息数大于 5」且会话仍存在的才立即收集
    assert sorted(flushed) == ["s1", "s4"]
    assert collect.await_count == 2


async def test_flush_pending_collects_sessions_with_unsummarized_blocks() -> None:
    """此前总结失败的 block 即使当前 block 没有积压也会重试"""
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector

    session_module = importlib.import_module("nonebot_plugin_chat.core.session")
    collector = EventCollector()
    groups = {"s1": _fake_session("s1", 0, unsummarized=[3])}

    collect = AsyncMock()
    with (
        patch.object(collector, "_collect", collect),
        patch.object(session_module, "groups", groups),
    ):
        flushed = await collector.flush_pending()

    assert flushed == ["s1"]
    collect.assert_awaited_once()


async def test_flush_pending_returns_empty_without_backlog() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector

    session_module = importlib.import_module("nonebot_plugin_chat.core.session")
    collector = EventCollector()
    groups = {"s1": _fake_session("s1", 5), "s2": _fake_session("s2", 1)}

    collect = AsyncMock()
    with (
        patch.object(collector, "_collect", collect),
        patch.object(session_module, "groups", {}),
    ):
        assert await collector.flush_pending() == []
    with (
        patch.object(collector, "_collect", collect),
        patch.object(session_module, "groups", groups),
    ):
        assert await collector.flush_pending() == []

    collect.assert_not_awaited()


async def test_flush_pending_custom_threshold() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector

    session_module = importlib.import_module("nonebot_plugin_chat.core.session")
    collector = EventCollector()
    groups = {"s1": _fake_session("s1", 2)}

    with (
        patch.object(collector, "_collect", AsyncMock()),
        patch.object(session_module, "groups", groups),
    ):
        assert await collector.flush_pending(min_pending=1) == ["s1"]


async def test_get_pending_message_count_reads_context() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector

    session_module = importlib.import_module("nonebot_plugin_chat.core.session")
    collector = EventCollector()
    groups = {"s1": _fake_session("s1", 7)}

    with patch.object(session_module, "groups", groups):
        assert collector.get_pending_message_count("s1") == 7
        assert collector.get_pending_message_count("missing") == 0


async def test_flush_pending_collects_all_sessions_beyond_concurrency_limit() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector

    session_module = importlib.import_module("nonebot_plugin_chat.core.session")
    collector = EventCollector()
    session_ids = [f"s{i}" for i in range(collector.FLUSH_PENDING_CONCURRENCY * 2 + 1)]
    groups = {session_id: _fake_session(session_id, 6) for session_id in session_ids}

    collect = AsyncMock()
    with (
        patch.object(collector, "_collect", collect),
        patch.object(session_module, "groups", groups),
    ):
        flushed = await collector.flush_pending()

    assert sorted(flushed) == sorted(session_ids)
    assert collect.await_count == len(session_ids)


async def test_planner_gather_context_flushes_before_reading_events() -> None:
    from nonebot_plugin_chat.core.ego import planner as planner_module

    _, collector = _event_collector_singleton()
    calls: list[str] = []

    async def flush_pending() -> list[str]:
        calls.append("flush")
        return []

    async def get_all_events_summary(date=None, since=None) -> str:
        calls.append(f"summary:{date}")
        return "事件摘要"

    with (
        patch.object(collector, "flush_pending", AsyncMock(side_effect=flush_pending)),
        patch.object(collector, "get_all_events_summary", AsyncMock(side_effect=get_all_events_summary)),
    ):
        result = await planner_module.Planner(None)._gather_context("2026-09-16")

    assert calls == ["flush", "summary:2026-09-16"]
    assert result == "事件摘要"


async def test_proactive_decide_flushes_before_reading_events() -> None:
    from nonebot_plugin_chat.core.ego import proactive_chat_ctrl as ctrl_module
    from nonebot_plugin_chat.core.ego.proactive_chat_ctrl import ProactiveChatController, ProactiveDecision

    _, collector = _event_collector_singleton()
    calls: list[str] = []

    async def flush_pending() -> list[str]:
        calls.append("flush")
        return []

    async def get_events_summary_since(cursor) -> str:
        calls.append("events")
        return "事件摘要"

    moonlark_main = SimpleNamespace(
        planner=SimpleNamespace(get_plan_text=lambda: "计划"),
        get_relevant_notes=AsyncMock(return_value="备注"),
    )
    controller = ProactiveChatController(moonlark_main)

    with (
        patch.object(collector, "flush_pending", AsyncMock(side_effect=flush_pending)),
        patch.object(collector, "get_decision_cursor", lambda: None),
        patch.object(collector, "advance_decision_cursor", lambda *args, **kwargs: None),
        patch.object(collector, "get_events_summary_since", AsyncMock(side_effect=get_events_summary_since)),
        patch.object(ctrl_module, "get_messages", AsyncMock(return_value=[])),
        patch.object(ctrl_module, "fetch_json", AsyncMock(return_value=ProactiveDecision(skip=True))),
        patch.object(controller, "_get_recent_sends", AsyncMock(return_value="发送记录")),
    ):
        decision = await controller._llm_decide({"u1": {"nickname": "小明", "fav": 0.5}})

    assert decision is not None and decision.skip
    # 必须先补齐积压事件，再读取决策事件
    assert calls == ["flush", "events"]
