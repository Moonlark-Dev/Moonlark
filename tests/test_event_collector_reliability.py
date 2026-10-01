"""事件收集器可靠性测试：内容规整、收集失败重试、收集间隔与缓存上限一致"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector


def test_collection_interval_matches_cache_limit() -> None:
    """收集间隔必须等于 clean_cached_message 的缓存上限（50）

    间隔大于缓存上限时，两批之间的消息永远不会被任何一次收集看到
    （间隔 100 时会漏掉一半消息）。
    """
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector

    assert EventCollector.COLLECTION_INTERVAL == 50


def test_normalize_event_content_coerces_types() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import normalize_event_content

    # 字符串被收敛为单元素列表，非列表/字符串被清空
    normalized = normalize_event_content({"topics": "话题A", "events": ["事件A", "", 42], "extra": 1})
    assert normalized is not None
    assert normalized["topics"] == ["话题A"]
    assert normalized["events"] == ["事件A", "42"]
    # 原始的额外字段保留
    assert normalized["extra"] == 1

    # 完全没有 topics/events 时给出空列表而不是 None
    normalized = normalize_event_content({})
    assert normalized == {"topics": [], "events": []}

    # 非对象无法规整
    assert normalize_event_content(["不是对象"]) is None
    assert normalize_event_content("字符串") is None


def test_format_event_content_is_robust() -> None:
    from nonebot_plugin_chat.core.ego.event_collector import format_event_content

    content = json.dumps({"topics": ["t1", "t2"], "events": ["e1"]}, ensure_ascii=False)
    text = format_event_content(content)
    assert "话题: t1, t2" in text
    assert "- e1" in text

    # 结构异常（topics 是字符串）不再抛 TypeError，而是正常渲染
    weird = format_event_content('{"topics": "t", "events": 123}')
    assert "话题: t" in weird

    # 非 JSON 内容降级为原文片段
    assert format_event_content("很久以前的原始记录") == "很久以前的原始记录"


async def test_collect_failure_restores_counter_for_retry() -> None:
    """收集失败时计数补回阈值，下一条消息会触发重试（避免事件永久丢失）"""
    import importlib

    # ego 包把 event_collector 这个名字重绑成了单例，必须按模块路径导入
    ec_module = importlib.import_module("nonebot_plugin_chat.core.ego.event_collector")
    collector = ec_module.EventCollector()
    session = SimpleNamespace(
        session_id="pytest_reliability_group",
        get_cached_messages_string=AsyncMock(return_value="[10:00:00] 小明: 你好"),
        get_session_name=AsyncMock(return_value="测试群"),
    )
    collector._session_message_counters[session.session_id] = 0

    with (
        patch.object(ec_module, "get_message_text", AsyncMock(return_value="身份")),
        patch.object(ec_module, "fetch_json", AsyncMock(side_effect=RuntimeError("上游炸了"))),
    ):
        await collector._collect(session)  # type: ignore[arg-type]

    assert collector._session_message_counters[session.session_id] == collector.COLLECTION_INTERVAL


async def test_collect_stores_normalized_content() -> None:
    """模型返回的非预期结构会被规整后再入库"""
    import importlib

    # ego 包把 event_collector 这个名字重绑成了单例，必须按模块路径导入
    ec_module = importlib.import_module("nonebot_plugin_chat.core.ego.event_collector")
    collector = ec_module.EventCollector()
    session = SimpleNamespace(
        session_id="pytest_reliability_group2",
        get_cached_messages_string=AsyncMock(return_value="[10:00:00] 小明: 你好"),
        get_session_name=AsyncMock(return_value="测试群"),
    )
    added: list = []

    class _DB:
        def add(self, obj: object) -> None:
            added.append(obj)

        async def commit(self) -> None:
            return None

    db_cm = AsyncMock()
    db_cm.__aenter__.return_value = _DB()

    with (
        patch.object(ec_module, "get_message_text", AsyncMock(return_value="身份")),
        patch.object(ec_module, "fetch_json", AsyncMock(return_value={"topics": "话题A", "events": ["事件A"]})),
        patch.object(ec_module, "get_session", lambda: db_cm),
    ):
        await collector._collect(session)  # type: ignore[arg-type]

    assert len(added) == 1
    stored = json.loads(added[0].content)
    assert stored["topics"] == ["话题A"]
    assert stored["events"] == ["事件A"]
