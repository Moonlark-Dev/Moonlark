"""会话元数据中的历史事件只渲染 events 文本，不再塞入整段事件 JSON"""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def test_format_events_only_returns_events_text() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import format_events_only

    content = json.dumps({"topics": ["周末计划"], "events": ["约好周六去爬山", "聊到了新番"]}, ensure_ascii=False)
    assert format_events_only(content) == "约好周六去爬山；聊到了新番"


def test_format_events_only_falls_back_to_raw_text() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import format_events_only

    # 非 JSON（旧数据）与非对象结构都降级为原文片段，不抛异常
    assert format_events_only("很久以前的原始记录") == "很久以前的原始记录"
    assert format_events_only('["不是对象"]') == '["不是对象"]'


async def test_session_context_renders_events_without_json() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import event_collector
    from nonebot_plugin_chat.core.ego.moonlark_main import moonlark_main

    event = SimpleNamespace(
        created_at=datetime(2026, 11, 14, 9, 30),
        content=json.dumps({"topics": ["周末计划"], "events": ["约好周六去爬山"]}, ensure_ascii=False),
    )
    with (
        patch.object(event_collector, "get_session_events", AsyncMock(return_value=[event])),
        patch.object(moonlark_main.planner, "get_plan_text", return_value=""),
    ):
        context = await moonlark_main.get_session_context("pytest_meta_events")

    assert "[09:30] 约好周六去爬山" in context
    assert "topics" not in context
    assert "{" not in context


async def test_session_context_skips_event_without_events() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import event_collector
    from nonebot_plugin_chat.core.ego.moonlark_main import moonlark_main

    event = SimpleNamespace(
        created_at=datetime(2026, 11, 14, 9, 30),
        content=json.dumps({"topics": ["只有话题"], "events": []}, ensure_ascii=False),
    )
    with (
        patch.object(event_collector, "get_session_events", AsyncMock(return_value=[event])),
        patch.object(moonlark_main.planner, "get_plan_text", return_value=""),
    ):
        context = await moonlark_main.get_session_context("pytest_meta_events")

    assert context == ""
