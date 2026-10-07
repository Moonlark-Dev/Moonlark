"""Chat Context 单元测试：前导消息、index / block 游标、锁与缓冲队列、滑动窗口、归档"""

from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import AsyncMock, patch

import pytest


def _make_session(session_id: str = "qq_1") -> Any:
    processor = SimpleNamespace(
        generate_system_prompt=AsyncMock(return_value={"role": "system", "content": "系统提示"}),
        generate_session_info=AsyncMock(return_value="会话元数据"),
    )
    return SimpleNamespace(session_id=session_id, processor=processor, lang_str="zh_hans")


def _make_context(session: Optional[Any] = None) -> Any:
    from nonebot_plugin_chat.core.context import ChatContext

    return ChatContext(session or _make_session())


class _FakeDB:
    """记录 merge / execute / commit 的假 AsyncSession"""

    def __init__(self, scalar_value: Any = None) -> None:
        self.merged: dict[tuple, Any] = {}
        self.scalar_value = scalar_value
        self.executed = 0
        self.commits = 0

    async def merge(self, obj: Any) -> Any:
        self.merged[(obj.session_id, obj.context_index, obj.index)] = obj
        return obj

    async def execute(self, _stmt: Any) -> Any:
        self.executed += 1
        return None

    async def scalar(self, _stmt: Any) -> Any:
        return self.scalar_value

    async def commit(self) -> None:
        self.commits += 1

    async def __aenter__(self) -> "_FakeDB":
        return self

    async def __aexit__(self, *_: Any) -> bool:
        return False


async def _initialized_context(db: _FakeDB) -> Any:
    context = _make_context()
    with patch.object(importlib.import_module("nonebot_plugin_chat.core.context"), "get_session", lambda: db):
        await context._initialize_context()
    return context


def _row(
    context_index: int,
    index: int,
    role: str,
    content: Any,
    *,
    block_id: int = 0,
    sub_type: str = "",
    timestamp: Optional[datetime] = None,
    tool_calls: Optional[list] = None,
    tool_call_id: Optional[str] = None,
    display_only: bool = False,
) -> Any:
    from nonebot_plugin_chat.models import ChatContextMessage

    return ChatContextMessage(
        session_id="qq_1",
        context_index=context_index,
        index=index,
        block_id=block_id,
        role=role,
        sub_type=sub_type,
        timestamp=timestamp or datetime.now(),
        content=json.dumps(content, ensure_ascii=False),
        data=None,
        display_only=display_only,
        tool_calls=json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
        tool_call_id=tool_call_id,
        trigger_type="none",
        request_id=None,
    )


async def test_initialize_context_injects_system_and_meta() -> None:
    db = _FakeDB()
    context = await _initialized_context(db)

    assert [message.role for message in context.messages[:2]] == ["system", "user"]
    assert context.messages[1].sub_type == "meta"
    assert all(message.block_id == 0 for message in context.messages)
    assert [message.index for message in context.messages] == [0, 1]
    assert context.thread_id == "qq_1:0"
    # 立即触发一次保存
    assert db.commits == 1
    assert set(db.merged) == {("qq_1", 0, 0), ("qq_1", 0, 1)}


async def test_push_assigns_index_and_shares_block() -> None:
    context = await _initialized_context(_FakeDB())
    first = await context.push_user_message("你好", sub_type="message", data={"content": "你好"})
    second = await context.push_user_message("事件", sub_type="event", trigger_type="all")

    assert (first.index, second.index) == (2, 3)
    assert first.block_id == second.block_id == context.current_block_id == 1
    assert context.pending_block_message_count == 2


async def test_freeze_block_advances_block_id() -> None:
    context = await _initialized_context(_FakeDB())
    await context.push_user_message("a")

    assert context.freeze_block(context.current_block_id) is True
    assert context.unsummarized_blocks == [1]
    # 已经冻结的 block 不能再冻结
    assert context.freeze_block(1) is False

    later = await context.push_user_message("b")
    assert later.block_id == 2
    context.mark_block_summarized(1)
    assert context.unsummarized_blocks == []


async def test_cached_messages_only_include_processor_json() -> None:
    context = await _initialized_context(_FakeDB())
    await context.push_user_message("你好", sub_type="message", data={"content": "你好", "self": False})
    await context.push_assistant_message("回复", data={"content": "回复", "self": True}, display_only=True)
    await context.push_user_message("提示", sub_type="event")

    cached = context.cached_messages
    assert [message["content"] for message in cached] == ["你好", "回复"]
    # display_only 是独立的列，不会混进 processor 解析出来的 json
    assert all("display_only" not in message for message in cached)
    assert [message.display_only for message in context.messages[-3:]] == [False, True, False]


async def test_display_only_message_stays_out_of_llm_list() -> None:
    db = _FakeDB()
    context = await _initialized_context(db)
    await context.push_user_message("你好", sub_type="message", data={"content": "你好"})
    await context.push_assistant_message("回复", data={"content": "回复"}, display_only=True)

    with patch.object(importlib.import_module("nonebot_plugin_chat.core.context"), "get_session", lambda: db):
        messages = await context.build_openai_messages()

    assert [message["role"] for message in messages] == ["system", "user", "user"]
    assert [message["content"] for message in messages] == ["系统提示", "会话元数据", "你好"]


async def test_ensure_preamble_repairs_broken_head() -> None:
    db = _FakeDB()
    context = _make_context()
    from nonebot_plugin_chat.core.context import ContextMessage

    context._messages = [
        ContextMessage(
            session_id="qq_1",
            context_index=0,
            index=5,
            block_id=1,
            role="user",
            sub_type="message",
            timestamp=datetime.now(),
            content="你好",
        )
    ]
    with patch.object(importlib.import_module("nonebot_plugin_chat.core.context"), "get_session", lambda: db):
        await context._ensure_preamble()

    assert [message.role for message in context.messages[:3]] == ["system", "user", "user"]
    assert context.messages[1].sub_type == "meta"
    # 修复后的前导消息仍然排在原有消息之前
    assert context.messages[0].index < context.messages[1].index < context.messages[2].index


async def test_repair_tool_pairing_removes_orphans() -> None:
    db = _FakeDB()
    context = await _initialized_context(db)
    await context.push_user_message("你好", sub_type="message", data={"content": "你好"})
    orphan_assistant = await context.push_assistant_message(
        None, tool_calls=[{"id": "call-1", "type": "function", "function": {"name": "f", "arguments": "{}"}}]
    )
    lonely_tool = await context.push_tool_message("结果", "call-2")

    ctx_module = importlib.import_module("nonebot_plugin_chat.core.context")
    with patch.object(ctx_module, "get_session", lambda: db):
        await context._repair_tool_pairing()

    # 孤立的工具调用删除整个 assistant 消息，孤立的工具返回单独删除
    assert all(message is not orphan_assistant for message in context.messages)
    assert all(message is not lonely_tool for message in context.messages)
    assert all(message.role not in ("assistant", "tool") for message in context.messages[2:])


async def test_absorb_messages_only_appends_new_tail() -> None:
    db = _FakeDB()
    context = await _initialized_context(db)
    known = [
        {"role": "system", "content": "系统提示"},
        {"role": "user", "content": "会话元数据"},
    ]
    assert await context.absorb_messages(known, "req-1") == []

    added = await context.absorb_messages([*known, {"role": "assistant", "content": "哦"}], "req-1")
    assert len(added) == 1
    assert added[0].role == "assistant"
    assert added[0].request_id == "req-1"
    assert added[0].index == 2


async def test_request_id_only_marks_message_queue_messages() -> None:
    """request id 只打在 message queue 推送上来的消息（LLM 输出与工具返回）上

    user / system 消息（注入进请求的图片、Jev 补发提示等）不带 request id，
    请求失败时不会跟着被删掉。
    """
    db = _FakeDB()
    context = await _initialized_context(db)
    known = [
        {"role": "system", "content": "系统提示"},
        {"role": "user", "content": "会话元数据"},
    ]
    messages = [
        *known,
        {"role": "user", "content": "注入的图片或提示"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "工具返回"},
    ]
    added = await context.absorb_messages(messages, "req-1")

    assert [message.role for message in added] == ["user", "assistant", "tool"]
    assert [message.request_id for message in added] == [None, "req-1", "req-1"]


async def test_cursor_buffers_processor_messages_and_releases() -> None:
    from nonebot_plugin_chat.core.context import MessageCursorClosed

    db = _FakeDB()
    context = await _initialized_context(db)
    cursor = await context.acquire_cursor()
    assert context.locked

    await context.push_user_message("普通消息")
    # 未触发 all 的消息留在 processor 缓冲队列里，不进入上下文
    assert all(message.content != "普通消息" for message in context.messages)
    assert cursor.drain() == []

    await context.push_user_message("插嘴", trigger_type="all")
    # 出现 trigger_type=all 时整个缓冲队列移交给 message queue
    drained = cursor.drain()
    assert [message.content for message in drained] == ["普通消息", "插嘴"]
    assert [message.content for message in context.messages[-2:]] == ["普通消息", "插嘴"]

    await cursor.report(True)
    assert not context.locked
    with pytest.raises(MessageCursorClosed):
        cursor.drain()


async def test_failed_request_discards_its_messages() -> None:
    db = _FakeDB()
    context = await _initialized_context(db)
    cursor = await context.acquire_cursor()
    known = [
        {"role": "system", "content": "系统提示"},
        {"role": "user", "content": "会话元数据"},
    ]
    await context.absorb_messages(
        [*known, {"role": "user", "content": "注入的图片"}, {"role": "assistant", "content": "失败的输出"}],
        cursor.request_id,
    )
    await context.push_user_message("处理器消息")

    ctx_module = importlib.import_module("nonebot_plugin_chat.core.context")
    with patch.object(ctx_module, "get_session", lambda: db):
        await cursor.report(False)

    assert all(message.content != "失败的输出" for message in context.messages)
    # 注入进请求的 user 消息不受 request id 影响，不会被误删
    assert any(message.content == "注入的图片" for message in context.messages)
    # processor 缓冲队列在解锁时全部加入上下文
    assert any(message.content == "处理器消息" for message in context.messages)


async def test_restore_resets_when_last_message_is_before_2am() -> None:
    db = _FakeDB(scalar_value=4)
    context = _make_context()
    rows = [
        _row(4, 0, "system", "系统提示"),
        _row(4, 1, "user", "会话元数据", sub_type="meta"),
        _row(4, 2, "user", "昨天的消息", block_id=1, sub_type="message", timestamp=datetime.now() - timedelta(days=1)),
    ]
    ctx_module = importlib.import_module("nonebot_plugin_chat.core.context")
    with (
        patch.object(ctx_module, "get_session", lambda: db),
        patch.object(context, "_load_rows", AsyncMock(return_value=rows)),
        patch.object(context, "_block_has_event", AsyncMock(return_value=False)),
    ):
        await context.restore()

    # 最后一条消息早于当天 2:00：立即 reset 到新的 context index
    assert context.context_index == 5
    assert [message.role for message in context.messages[:2]] == ["system", "user"]
    assert context.messages[1].sub_type == "meta"


async def test_restore_keeps_context_when_recent() -> None:
    db = _FakeDB(scalar_value=4)
    context = _make_context()
    rows = [
        _row(4, 0, "system", "系统提示"),
        _row(4, 1, "user", "会话元数据", sub_type="meta"),
        _row(4, 2, "user", "刚才的消息", block_id=2, sub_type="message"),
        _row(4, 3, "assistant", "回复", block_id=2),
    ]
    ctx_module = importlib.import_module("nonebot_plugin_chat.core.context")
    with (
        patch.object(ctx_module, "get_session", lambda: db),
        patch.object(context, "_load_rows", AsyncMock(return_value=rows)),
        patch.object(context, "_block_has_event", AsyncMock(return_value=False)),
        patch.object(context, "_reset_threshold", lambda: datetime.now() - timedelta(hours=1)),
    ):
        await context.restore()

    assert context.context_index == 4
    assert len(context.messages) == 4
    assert context.current_block_id == 2
    assert context.pending_block_message_count == 2
    assert context.thread_id == "qq_1:4"


async def test_restore_starts_new_block_when_latest_is_summarized() -> None:
    db = _FakeDB(scalar_value=4)
    context = _make_context()
    rows = [
        _row(4, 0, "system", "系统提示"),
        _row(4, 1, "user", "会话元数据", sub_type="meta"),
        _row(4, 2, "user", "消息", block_id=2, sub_type="message"),
    ]
    ctx_module = importlib.import_module("nonebot_plugin_chat.core.context")
    with (
        patch.object(ctx_module, "get_session", lambda: db),
        patch.object(context, "_load_rows", AsyncMock(return_value=rows)),
        patch.object(context, "_block_has_event", AsyncMock(return_value=True)),
        patch.object(context, "_reset_threshold", lambda: datetime.now() - timedelta(hours=1)),
    ):
        await context.restore()

    assert context.current_block_id == 3
    assert context.pending_block_message_count == 0
    assert (await context.push_user_message("新消息")).block_id == 3


async def test_sliding_window_truncates_irrelevant_blocks() -> None:
    db = _FakeDB()
    context = await _initialized_context(db)
    await context.push_user_message("旧话题")
    assert context.freeze_block(context.current_block_id)
    await context.push_user_message("新话题")
    latest = await context.push_assistant_message("新话题的回复")
    latest.timestamp = datetime.now() - timedelta(minutes=30)
    latest.request_id = "req-old"

    ctx_module = importlib.import_module("nonebot_plugin_chat.core.context")
    with (
        patch.object(ctx_module, "get_session", lambda: db),
        patch.object(context, "_get_block_events_text", AsyncMock(side_effect=lambda block_id: "事件")),
        patch.object(context, "_block_still_relevant", AsyncMock(return_value=False)),
    ):
        assert await context.run_sliding_window() is True

    # 前导消息保留，不再相关的 block 及其之前的消息全部删除
    assert [message.role for message in context.messages[:2]] == ["system", "user"]
    assert context.messages[1].sub_type == "meta"
    assert all(message.block_id in (0, 2) for message in context.messages)


async def test_sliding_window_skipped_when_recent() -> None:
    db = _FakeDB()
    context = await _initialized_context(db)
    await context.push_user_message("新话题")
    latest = await context.push_assistant_message("回复")
    latest.request_id = "req-new"

    ctx_module = importlib.import_module("nonebot_plugin_chat.core.context")
    with (
        patch.object(ctx_module, "get_session", lambda: db),
        patch.object(context, "_get_block_events_text", AsyncMock()) as events,
    ):
        assert await context.run_sliding_window() is False
    events.assert_not_awaited()


async def test_cached_messages_converts_each_message_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """cached_messages 重建时不能重复转换已经转换过的消息

    每条带图消息的转换都要做 base64 解码，而 cached_messages 在一次消息处理里会被
    读取很多次（每次 _commit 都会让缓存失效）。此前每次访问都要把整个上下文重新
    转换一遍，上下文涨到几千条时事件循环会被拖死。
    """
    import importlib

    ctx_module = importlib.import_module("nonebot_plugin_chat.core.context")
    context = await _initialized_context(_FakeDB())
    # 消息数可能超过一个 block 的容量，这些用例不需要真的去收集事件
    from nonebot_plugin_chat.core.ego.event_collector import event_collector

    monkeypatch.setattr(event_collector, "request_collection", lambda _session: None)

    calls = 0
    original = ctx_module._extract_images

    def _counting(content: Any) -> Any:
        nonlocal calls
        calls += 1
        return original(content)

    monkeypatch.setattr(ctx_module, "_extract_images", _counting)

    def _image_content(index: int) -> list:
        return [
            {"type": "text", "text": f"第 {index} 条"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        ]

    for i in range(5):
        await context.push_user_message(
            _image_content(i), sub_type="message", data={"content": f"第 {i} 条", "self": False}
        )

    assert calls == 0  # 还没人读
    assert len(context.cached_messages) == 5
    assert calls == 5

    # 又来一条消息：只应该转换这一条新的
    await context.push_user_message(_image_content(5), sub_type="message", data={"content": "第 5 条", "self": False})
    assert len(context.cached_messages) == 6
    assert calls == 6, "已经转换过的消息被重复转换"


async def test_cached_messages_only_converts_visible_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """只转换对外可见的最近 CACHED_MESSAGE_LIMIT 条，滑出窗口的消息释放图片二进制"""
    import importlib

    from nonebot_plugin_chat.core.context import CACHED_MESSAGE_LIMIT

    ctx_module = importlib.import_module("nonebot_plugin_chat.core.context")
    context = await _initialized_context(_FakeDB())
    # 消息数可能超过一个 block 的容量，这些用例不需要真的去收集事件
    from nonebot_plugin_chat.core.ego.event_collector import event_collector

    monkeypatch.setattr(event_collector, "request_collection", lambda _session: None)

    calls = 0
    original = ctx_module._extract_images

    def _counting(content: Any) -> Any:
        nonlocal calls
        calls += 1
        return original(content)

    monkeypatch.setattr(ctx_module, "_extract_images", _counting)

    def _push(index: int) -> Any:
        return context.push_user_message(
            [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}],
            sub_type="message",
            data={"content": f"第 {index} 条", "self": False},
        )

    # 先读一次，让窗口覆盖最早的一批消息
    for i in range(10):
        await _push(i)
    assert len(context.cached_messages) == 10
    assert calls == 10

    total = CACHED_MESSAGE_LIMIT + 10
    for i in range(10, total):
        await _push(i)
    context.invalidate_cached_messages()

    assert len(context.cached_messages) == CACHED_MESSAGE_LIMIT
    # 每条消息只转换一次：10 条旧的 + 窗口里的新消息
    assert calls == total, "已经转换过的消息被重复转换"
    # 滑出窗口的消息不再保留图片二进制
    window_start = len(context.messages) - CACHED_MESSAGE_LIMIT
    assert all(message._cached_message is None for message in context.messages[:window_start])


async def test_cached_messages_skips_conversion_outside_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """从未被读过时，一次访问只转换窗口内的消息"""
    import importlib

    from nonebot_plugin_chat.core.context import CACHED_MESSAGE_LIMIT

    ctx_module = importlib.import_module("nonebot_plugin_chat.core.context")
    context = await _initialized_context(_FakeDB())
    # 消息数可能超过一个 block 的容量，这些用例不需要真的去收集事件
    from nonebot_plugin_chat.core.ego.event_collector import event_collector

    monkeypatch.setattr(event_collector, "request_collection", lambda _session: None)

    calls = 0
    original = ctx_module._extract_images

    def _counting(content: Any) -> Any:
        nonlocal calls
        calls += 1
        return original(content)

    monkeypatch.setattr(ctx_module, "_extract_images", _counting)

    total = CACHED_MESSAGE_LIMIT + 30
    for i in range(total):
        await context.push_user_message(
            [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}],
            sub_type="message",
            data={"content": f"第 {i} 条", "self": False},
        )

    assert len(context.cached_messages) == CACHED_MESSAGE_LIMIT
    assert calls == CACHED_MESSAGE_LIMIT, "转换了窗口之外的消息"


async def test_context_message_signature_is_cached_and_invalidated() -> None:
    """消息指纹只算一次，content 被改写后必须重算"""
    context = await _initialized_context(_FakeDB())
    message = await context.push_user_message("你好", sub_type="message", data={"content": "你好"})

    first = message.signature()
    assert message.signature() is first

    message.content = "改写后的内容"
    assert message.signature() is first  # 未声明改写时仍然命中缓存

    message.invalidate_signature()
    assert message.signature() != first


async def test_archive_expired_contexts_writes_json(tmp_path: Any) -> None:
    archive_module = importlib.import_module("nonebot_plugin_chat.core.context_archive")
    rows = [
        _row(2, 0, "system", "系统提示"),
        _row(2, 1, "user", "会话元数据", sub_type="meta"),
    ]
    deleted: list[tuple[str, int]] = []

    async def _delete(session_id: str, context_index: int) -> None:
        deleted.append((session_id, context_index))

    with (
        patch.object(archive_module, "_list_expired_contexts", AsyncMock(return_value=[("qq_1", 2)])),
        patch.object(archive_module, "_load_context", AsyncMock(return_value=rows)),
        patch.object(archive_module, "_delete_context", AsyncMock(side_effect=_delete)),
        patch.object(archive_module, "_active_context_indexes", AsyncMock(return_value={})),
        patch.object(
            archive_module, "_archive_path", lambda session_id, index: tmp_path / f"{session_id}_{index}.json"
        ),
    ):
        result = await archive_module.archive_expired_contexts()

    assert result.archived == [("qq_1", 2)]
    assert deleted == [("qq_1", 2)]
    payload = json.loads((tmp_path / "qq_1_2.json").read_text(encoding="utf-8"))
    assert payload["session_id"] == "qq_1"
    assert payload["message_count"] == 2
    assert payload["messages"][0]["role"] == "system"


async def test_archive_skips_active_context() -> None:
    archive_module = importlib.import_module("nonebot_plugin_chat.core.context_archive")
    with (
        patch.object(archive_module, "_list_expired_contexts", AsyncMock(return_value=[("qq_1", 2)])),
        patch.object(archive_module, "_active_context_indexes", AsyncMock(return_value={"qq_1": 2})),
        patch.object(archive_module, "archive_context", AsyncMock()) as archive,
    ):
        result = await archive_module.archive_expired_contexts()

    assert result.archived == []
    archive.assert_not_awaited()
