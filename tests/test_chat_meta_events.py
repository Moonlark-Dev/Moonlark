"""会话元数据中的历史事件只渲染 events 文本，并注明事件发生在昨天还是今天"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
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


async def test_session_context_renders_events_without_json_and_labels_their_date() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import event_collector
    from nonebot_plugin_chat.core.ego.moonlark_main import moonlark_main

    now = datetime.now()
    # 用相对当前时间的事件，避免测试依赖运行日期；事件按时间升序返回
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    events = [
        SimpleNamespace(
            created_at=today_start - timedelta(days=1) + timedelta(hours=23, minutes=50),
            content=json.dumps({"topics": ["周末计划"], "events": ["约好周六去爬山"]}, ensure_ascii=False),
        ),
        SimpleNamespace(
            created_at=today_start,
            content=json.dumps({"topics": ["新番"], "events": ["聊到了新番"]}, ensure_ascii=False),
        ),
    ]
    with (
        patch.object(event_collector, "get_session_events", AsyncMock(return_value=events)),
        patch.object(moonlark_main.planner, "get_plan_text", return_value=""),
    ):
        context = await moonlark_main.get_session_context("pytest_meta_events")

    # 只写时分不足以区分「昨天」与「今天早些时候」，两条事件都必须带上日期标签
    assert "[前一天 23:50] 约好周六去爬山" in context
    assert "[今天早些时候 00:00] 聊到了新番" in context
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
