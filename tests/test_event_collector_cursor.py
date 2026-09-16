"""会话事件收集器测试：决策游标与增量事件摘要"""

from __future__ import annotations

import importlib
import json
from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector
    from nonebot_plugin_chat.models import SessionEvent

SESSION_ID = "pytest_cursor_group"


def _event(event_id: int, topics: list[str], events: list[str]) -> "SessionEvent":
    from nonebot_plugin_chat.models import SessionEvent

    return SessionEvent(
        id=event_id,
        session_id=SESSION_ID,
        date="2026-09-16",
        content=json.dumps({"topics": topics, "events": events}, ensure_ascii=False),
    )


def _make_collector_with_rows(rows: list["SessionEvent"]) -> tuple["EventCollector", dict]:
    """构造一个记录 execute 语句、并返回指定事件的 EventCollector"""
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector

    captured: dict = {}
    fake_scalars = SimpleNamespace(all=lambda: rows)
    fake_result = SimpleNamespace(scalars=lambda: fake_scalars)

    async def fake_execute(stmt: object) -> SimpleNamespace:
        captured["stmt"] = stmt
        return fake_result

    fake_db_session = SimpleNamespace(execute=fake_execute)
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = fake_db_session
    return EventCollector(), {"captured": captured, "session_cm": session_cm}


def test_decision_cursor_defaults_to_none() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector

    assert EventCollector().get_decision_cursor() is None


async def test_events_summary_since_cursor_filters_and_keeps_all_events() -> None:
    # 注意：ego 包把 event_collector 这个名字重绑成了单例，必须按模块路径导入
    ec = importlib.import_module("nonebot_plugin_chat.core.ego.event_collector")

    rows = [_event(1, ["话题A"], ["事件A"]), _event(2, ["话题B"], ["事件B"])]
    collector, ctx = _make_collector_with_rows(rows)
    cursor = datetime(2026, 9, 16, 12, 0, 0)

    with patch.object(ec, "get_session", return_value=ctx["session_cm"]):
        summary = await collector.get_events_summary_since(cursor)

    stmt = str(ctx["captured"]["stmt"])
    # 只按游标过滤创建时间，不再限制当天日期
    assert "created_at >" in stmt
    assert "date =" not in stmt
    # 游标区间内不做会话去重，同一会话的多条新事件都应保留
    assert "话题A" in summary
    assert "话题B" in summary


async def test_events_summary_since_none_falls_back_to_today() -> None:
    # 注意：ego 包把 event_collector 这个名字重绑成了单例，必须按模块路径导入
    ec = importlib.import_module("nonebot_plugin_chat.core.ego.event_collector")

    rows = [_event(1, ["话题A"], ["事件A"]), _event(2, ["话题B"], ["事件B"])]
    collector, ctx = _make_collector_with_rows(rows)

    with patch.object(ec, "get_session", return_value=ctx["session_cm"]):
        summary = await collector.get_events_summary_since(None)

    stmt = str(ctx["captured"]["stmt"])
    # 无游标时退回当天全部事件，并沿用每个会话只保留第一条的旧行为
    assert "date =" in stmt
    assert "created_at >" not in stmt
    assert "话题A" in summary
    assert "话题B" not in summary


def test_advance_decision_cursor() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector

    collector = EventCollector()
    moment = datetime(2026, 9, 16, 13, 30, 0)
    collector.advance_decision_cursor(moment)
    assert collector.get_decision_cursor() == moment

    collector.advance_decision_cursor()
    advanced = collector.get_decision_cursor()
    assert advanced is not None
    assert advanced != moment
