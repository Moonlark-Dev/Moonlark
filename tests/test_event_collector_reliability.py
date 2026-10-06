"""事件收集器可靠性测试：内容规整、按 block 收集、收集失败重试"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector


def test_collection_interval_matches_block_limit() -> None:
    """收集间隔必须等于 chat context 的 block 上限（50）"""
    from nonebot_plugin_chat.core.context import BLOCK_MESSAGE_LIMIT
    from nonebot_plugin_chat.core.ego.event_collector import EventCollector

    assert EventCollector.COLLECTION_INTERVAL == BLOCK_MESSAGE_LIMIT == 50


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


class _FakeContext:
    """只实现 EventCollector 需要的那部分 ChatContext"""

    def __init__(self, history: str = "[10:00:00] 小明: 你好", pending: int = 50) -> None:
        self._history = history
        self.pending_block_message_count = pending
        self.current_block_id = 3
        self.unsummarized_blocks: list[int] = []
        self.summarized: list[int] = []

    def freeze_block(self, block_id: int) -> bool:
        if block_id != self.current_block_id:
            return False
        self.unsummarized_blocks.append(block_id)
        self.current_block_id = block_id + 1
        self.pending_block_message_count = 0
        return True

    def mark_block_summarized(self, block_id: int) -> None:
        self.summarized.append(block_id)
        if block_id in self.unsummarized_blocks:
            self.unsummarized_blocks.remove(block_id)

    def block_history_string(self, block_id: int) -> str:
        return self._history


def _fake_session(context: _FakeContext) -> Any:
    return SimpleNamespace(
        session_id="pytest_reliability_group",
        processor=SimpleNamespace(openai_messages=SimpleNamespace(context=context)),
        get_session_name=AsyncMock(return_value="测试群"),
    )


async def test_collect_failure_keeps_block_for_retry() -> None:
    """收集失败时 block 记为未总结，下一次收集会重试（避免事件永久丢失）"""
    import importlib

    # ego 包把 event_collector 这个名字重绑成了单例，必须按模块路径导入
    ec_module = importlib.import_module("nonebot_plugin_chat.core.ego.event_collector")
    collector = ec_module.EventCollector()
    context = _FakeContext(pending=50)
    session = _fake_session(context)

    with (
        patch.object(ec_module, "get_message_text", AsyncMock(return_value="身份")),
        patch.object(ec_module, "fetch_json", AsyncMock(side_effect=RuntimeError("上游炸了"))),
    ):
        await collector._collect(session, min_pending=collector.COLLECTION_INTERVAL - 1)

    assert context.summarized == []
    assert context.unsummarized_blocks == [3]


async def test_collect_stores_normalized_content_with_block_id() -> None:
    """模型返回的非预期结构会被规整后再入库，并带上 block_id"""
    import importlib

    # ego 包把 event_collector 这个名字重绑成了单例，必须按模块路径导入
    ec_module = importlib.import_module("nonebot_plugin_chat.core.ego.event_collector")
    collector = ec_module.EventCollector()
    context = _FakeContext(pending=50)
    session = _fake_session(context)
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
        await collector._collect(session, min_pending=collector.COLLECTION_INTERVAL - 1)

    assert len(added) == 1
    stored = json.loads(added[0].content)
    assert stored["topics"] == ["话题A"]
    assert stored["events"] == ["事件A"]
    assert added[0].block_id == 3
    assert context.summarized == [3]
    assert context.unsummarized_blocks == []


async def test_collect_retries_unsummarized_block() -> None:
    """此前失败的 block 会在下一次收集时重试"""
    import importlib

    ec_module = importlib.import_module("nonebot_plugin_chat.core.ego.event_collector")
    collector = ec_module.EventCollector()
    context = _FakeContext(pending=0)
    context.unsummarized_blocks = [2]
    session = _fake_session(context)

    class _DB:
        def add(self, obj: object) -> None:
            return None

        async def commit(self) -> None:
            return None

    db_cm = AsyncMock()
    db_cm.__aenter__.return_value = _DB()

    with (
        patch.object(ec_module, "get_message_text", AsyncMock(return_value="身份")),
        patch.object(ec_module, "fetch_json", AsyncMock(return_value={"topics": [], "events": ["旧事件"]})),
        patch.object(ec_module, "get_session", lambda: db_cm),
    ):
        await collector._collect(session, min_pending=collector.FLUSH_PENDING_THRESHOLD)

    assert context.summarized == [2]
    assert context.unsummarized_blocks == []


async def test_collect_does_not_freeze_block_below_threshold() -> None:
    """未达到阈值时不冻结 block（不能把不完整的 block 提前总结）"""
    import importlib

    ec_module = importlib.import_module("nonebot_plugin_chat.core.ego.event_collector")
    collector = ec_module.EventCollector()
    context = _FakeContext(pending=5)
    session = _fake_session(context)

    with patch.object(ec_module, "fetch_json", AsyncMock()) as fetch:
        await collector._collect(session, min_pending=collector.FLUSH_PENDING_THRESHOLD)

    fetch.assert_not_awaited()
    assert context.current_block_id == 3
    assert context.pending_block_message_count == 5
