"""事件收集器积压消息收集测试：planner 与主动私聊决策前必须先补齐会话事件"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def _event_collector_singleton():
    module = importlib.import_module("nonebot_plugin_chat.core.ego.event_collector")
    return module, module.event_collector


async def test_flush_pending_skips_sessions_at_or_below_threshold() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector

    session_module = importlib.import_module("nonebot_plugin_chat.core.session")
    collector = EventCollector()
    collector._session_message_counters.update({"s1": 6, "s2": 5, "s3": 0, "s4": 100, "s_missing": 7})
    groups = {key: SimpleNamespace(session_id=key) for key in ("s1", "s2", "s3", "s4")}

    collect = AsyncMock()
    with (
        patch.object(collector, "_collect", collect),
        patch.object(session_module, "groups", groups),
    ):
        flushed = await collector.flush_pending()

    # 只有「消息数大于 5」且会话仍存在的才立即收集
    assert flushed == ["s1", "s4"]
    assert collect.await_count == 2
    # 立即收集后计数清零，其余会话保持原样
    assert collector.get_pending_message_count("s1") == 0
    assert collector.get_pending_message_count("s4") == 0
    assert collector.get_pending_message_count("s2") == 5
    assert collector.get_pending_message_count("s3") == 0
    assert collector.get_pending_message_count("s_missing") == 0


async def test_flush_pending_returns_empty_without_backlog() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector

    session_module = importlib.import_module("nonebot_plugin_chat.core.session")
    collector = EventCollector()
    collector._session_message_counters.update({"s1": 5, "s2": 1})

    collect = AsyncMock()
    with (
        patch.object(collector, "_collect", collect),
        patch.object(session_module, "groups", {}),
    ):
        assert await collector.flush_pending() == []

    collect.assert_not_awaited()


async def test_flush_pending_custom_threshold() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector

    session_module = importlib.import_module("nonebot_plugin_chat.core.session")
    collector = EventCollector()
    collector._session_message_counters["s1"] = 2

    with (
        patch.object(collector, "_collect", AsyncMock()),
        patch.object(session_module, "groups", {"s1": SimpleNamespace(session_id="s1")}),
    ):
        assert await collector.flush_pending(min_pending=1) == ["s1"]


async def test_flush_pending_collects_all_sessions_beyond_concurrency_limit() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector

    session_module = importlib.import_module("nonebot_plugin_chat.core.session")
    collector = EventCollector()
    session_ids = [f"s{i}" for i in range(collector.FLUSH_PENDING_CONCURRENCY * 2 + 1)]
    collector._session_message_counters.update({session_id: 6 for session_id in session_ids})
    groups = {session_id: SimpleNamespace(session_id=session_id) for session_id in session_ids}

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
