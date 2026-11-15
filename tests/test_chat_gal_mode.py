"""私聊备选回复（``/gal-mode``）的回归测试

覆盖发送缓存的先进先出、备选回复清洗、一轮结束时的最终消息发送、主动停止时
丢弃缓存，以及 ``/gal-mode on|off`` 的落库逻辑。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest


def _make_manager() -> tuple[Any, Any]:
    """构造一个最小可用的 GalModeManager"""
    from nonebot_plugin_chat.core.gal_mode import GalModeManager

    session = SimpleNamespace(
        session_id="qq_1",
        nickname="小明",
        cached_messages=[],
        get_session_type=lambda: "private",
    )
    processor = SimpleNamespace(
        session=session,
        openai_messages=SimpleNamespace(last_thought=None),
        _latest_reasioning_content_cache="",
    )
    manager = GalModeManager(processor)
    manager._active = True
    return manager, processor


async def test_enqueue_keeps_current_message_and_flushes_previous() -> None:
    """每次 send_message 缓存当前消息，并把上一条挤出缓存的消息交回发送"""
    manager, _ = _make_manager()

    assert await manager.enqueue("第一条", None, 0) is None
    flushed = await manager.enqueue("第二条", "msg-1", 0)

    assert flushed is not None
    assert flushed.content == "第一条"
    assert flushed.reply_message_id is None
    assert manager.pending_contents == ["第二条"]
    assert manager.should_buffer()


async def test_has_sent_since_uses_buffered_messages() -> None:
    """本轮缓存过的消息在 Jev 判定里视为已发送，避免被误判漏发"""
    manager, _ = _make_manager()
    since = datetime.now()
    assert not manager.has_sent_since(since)

    await manager.enqueue("你好", None, 0)

    assert manager.has_sent_since(since)


def test_sanitize_suggestions_trims_dedupes_and_limits() -> None:
    """备选回复要清洗空白、去重、限制长度与条数"""
    from nonebot_plugin_chat.core.gal_mode import MAX_SUGGESTION_LENGTH, GalModeManager

    replies = [
        "  第一条\n",
        "第一条",
        "",
        "x" * (MAX_SUGGESTION_LENGTH + 20),
        "第三条",
        "第四条",
    ]

    suggestions = GalModeManager._sanitize_suggestions(replies)

    assert suggestions[0] == "第一条"
    assert len(suggestions[0]) == 3
    assert suggestions[1] == "x" * MAX_SUGGESTION_LENGTH
    assert suggestions[2] == "第三条"
    assert len(suggestions) == 3


async def test_finish_round_sends_last_message_with_suggestions() -> None:
    """一轮结束时把最后一条缓存消息连同备选回复一起发出"""
    manager, processor = _make_manager()
    processor.deliver_buffered_message = AsyncMock()
    manager._generate_suggestions = AsyncMock(return_value=["选项一", "选项二"])
    await manager.enqueue("最后一条", None, 0)

    await manager.finish_round()

    processor.deliver_buffered_message.assert_awaited_once()
    message, suggestions = processor.deliver_buffered_message.await_args.args
    assert message.content == "最后一条"
    assert suggestions == ["选项一", "选项二"]
    assert not manager.should_buffer()
    assert manager.pending_contents == []


async def test_finish_round_without_messages_does_nothing() -> None:
    """本轮没有调用 send_message 时不生成备选回复、也不发送消息"""
    manager, processor = _make_manager()
    processor.deliver_buffered_message = AsyncMock()
    manager._generate_suggestions = AsyncMock(return_value=[])

    await manager.finish_round()

    manager._generate_suggestions.assert_not_awaited()
    processor.deliver_buffered_message.assert_not_awaited()


async def test_generation_failure_still_sends_message() -> None:
    """备选回复生成失败时仍要发出最终消息（只是没有按钮）"""
    manager, processor = _make_manager()
    processor.deliver_buffered_message = AsyncMock()
    manager._generate_suggestions = AsyncMock(side_effect=RuntimeError("LLM 不可用"))
    await manager.enqueue("最后一条", None, 0)

    await manager.finish_round()

    message, suggestions = processor.deliver_buffered_message.await_args.args
    assert message.content == "最后一条"
    assert suggestions == []


async def test_abort_round_discards_buffered_message() -> None:
    """主动停止/超时后不再补发缓存消息"""
    manager, processor = _make_manager()
    processor.deliver_buffered_message = AsyncMock()
    manager._generate_suggestions = AsyncMock(return_value=["选项"])
    await manager.enqueue("不该发出的消息", None, 0)

    manager.abort_round()
    await manager.finish_round()

    processor.deliver_buffered_message.assert_not_awaited()
    assert not manager.should_buffer()


async def test_begin_round_snapshots_recent_messages_and_resets_buffer() -> None:
    """一轮开始时清空上一轮缓存，并记录回复前的最近 5 条对话"""
    manager, processor = _make_manager()
    manager._buffer.append(object())  # 上一轮残留
    manager._load_enabled = AsyncMock(return_value=True)
    processor.session.cached_messages = [
        {"nickname": "小明", "content": f"消息{i}", "self": False} for i in range(6)
    ] + [{"nickname": "Moonlark", "content": "我发过的", "self": True}]

    await manager.begin_round()

    assert manager.should_buffer()
    assert manager.pending_contents == []
    assert len(manager._recent_messages) == 5
    assert manager._recent_messages[-1] == "Moonlark: 我发过的"
    assert manager._recent_messages[0] == "小明: 消息2"


async def test_send_message_buffers_then_flushes_previous() -> None:
    """MessageProcessor.send_message 在缓存生效时只发送被挤出的上一条消息"""
    from nonebot_plugin_chat.core.processor import MessageProcessor

    manager, _ = _make_manager()
    processor = SimpleNamespace(
        gal_mode=manager,
        session=SimpleNamespace(
            get_session_type=lambda: "private",
            text=AsyncMock(return_value="消息发送成功。"),
        ),
        _deliver_message=AsyncMock(return_value="msg-id"),
    )

    result = await MessageProcessor.send_message(processor, "第一条")

    assert result == "消息发送成功。"
    processor._deliver_message.assert_not_awaited()

    result = await MessageProcessor.send_message(processor, "第二条")

    assert result == "消息发送成功。"
    processor._deliver_message.assert_awaited_once_with("第一条", None, 0)
    assert manager.pending_contents == ["第二条"]


async def test_gal_mode_command_persists_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """``/gal-mode on|off`` 写入 PrivateChatConfig.gal_mode"""
    from nonebot_plugin_chat.matcher import gal_mode as module

    class _Stop(Exception):
        pass

    finished: list[tuple[str, tuple[Any, ...]]] = []

    async def fake_finish(key: str, user_id: str, *args: Any) -> None:
        finished.append((key, args))
        raise _Stop

    monkeypatch.setattr(module, "private_message", AsyncMock(return_value=True))
    monkeypatch.setattr(module.lang, "finish", fake_finish)

    session = SimpleNamespace(get=AsyncMock(return_value=None), merge=AsyncMock(), commit=AsyncMock())
    message = SimpleNamespace(extract_plain_text=lambda: "on")

    with pytest.raises(_Stop):
        await module._(event=SimpleNamespace(), session=session, message=message, user_id="123")

    config = session.merge.await_args.args[0]
    assert config.user_id == "123"
    assert config.enabled is True
    assert config.gal_mode is True
    assert finished[0][0] == "command.gal_mode.enabled"

    existing = SimpleNamespace(enabled=True, gal_mode=True)
    session = SimpleNamespace(get=AsyncMock(return_value=existing), merge=AsyncMock(), commit=AsyncMock())
    message = SimpleNamespace(extract_plain_text=lambda: "off")

    with pytest.raises(_Stop):
        await module._(event=SimpleNamespace(), session=session, message=message, user_id="123")

    assert existing.gal_mode is False
    assert finished[-1][0] == "command.gal_mode.disabled"


async def test_gal_mode_command_is_private_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """群聊中使用 ``/gal-mode`` 只提示私聊可用，不写库"""
    from nonebot_plugin_chat.matcher import gal_mode as module

    class _Stop(Exception):
        pass

    finished: list[str] = []

    async def fake_finish(key: str, user_id: str, *args: Any) -> None:
        finished.append(key)
        raise _Stop

    monkeypatch.setattr(module, "private_message", AsyncMock(return_value=False))
    monkeypatch.setattr(module.lang, "finish", fake_finish)
    session = SimpleNamespace(get=AsyncMock(), merge=AsyncMock(), commit=AsyncMock())

    with pytest.raises(_Stop):
        await module._(
            event=SimpleNamespace(),
            session=session,
            message=SimpleNamespace(extract_plain_text=lambda: "on"),
            user_id="123",
        )

    assert finished == ["command.gal_mode.private_only"]
    session.merge.assert_not_awaited()


async def test_gal_mode_command_reports_current_state_without_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不带参数时只回报当前状态"""
    from nonebot_plugin_chat.matcher import gal_mode as module

    class _Stop(Exception):
        pass

    finished: list[str] = []

    async def fake_finish(key: str, user_id: str, *args: Any) -> None:
        finished.append(key)
        raise _Stop

    monkeypatch.setattr(module, "private_message", AsyncMock(return_value=True))
    monkeypatch.setattr(module.lang, "finish", fake_finish)
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(enabled=True, gal_mode=True)),
        merge=AsyncMock(),
        commit=AsyncMock(),
    )

    with pytest.raises(_Stop):
        await module._(
            event=SimpleNamespace(),
            session=session,
            message=SimpleNamespace(extract_plain_text=lambda: ""),
            user_id="123",
        )

    assert finished == ["command.gal_mode.current_on"]
    session.merge.assert_not_awaited()


async def test_gal_mode_prompt_renders_expected_inputs() -> None:
    """候选回复提示词包含全部参考信息与 JSON 输出要求"""
    from nonebot_plugin_openai.utils.message import get_message_text

    system = await get_message_text("gal_mode/system.md.jinja")
    user = await get_message_text(
        "gal_mode/user.md.jinja",
        recent_messages="小明: 你好\nMoonlark: 晚上好",
        sent_messages="- 晚上好呀",
        thought="今天也很有精神",
        mood="开心",
        mood_intensity=0.6,
        mood_reason="被夸了",
        tiredness=12,
        nickname="小明",
    )

    assert '"replies"' in system
    assert "1~3" in system
    for expected in ("小明: 你好", "晚上好呀", "今天也很有精神", "开心", "0.6", "被夸了", "12%", "小明"):
        assert expected in user


class _FakeQQBot:
    """仅用于 isinstance(bot, QQBot) 判断的假机器人"""


class _FakeUniMessage:
    """记录 style / keyboard / reply / send 调用的假 UniMessage"""

    instances: list["_FakeUniMessage"] = []

    def __init__(self, text: str = "") -> None:
        self.content = text
        self.styles: list[str] = []
        self.buttons: list[Any] = []
        self.reply_id: str | None = None
        self.send = AsyncMock(return_value=SimpleNamespace(msg_ids=[{"message_id": "mid-1"}]))
        _FakeUniMessage.instances.append(self)

    def style(self, content: str, style: str) -> "_FakeUniMessage":
        self.content = content
        self.styles.append(style)
        return self

    def text(self, text: str) -> "_FakeUniMessage":
        self.content = text
        return self

    def keyboard(self, *buttons: Any) -> "_FakeUniMessage":
        self.buttons = list(buttons)
        return self

    def reply(self, reply_id: str) -> "_FakeUniMessage":
        self.reply_id = reply_id
        return self

    def extract_plain_text(self) -> str:
        return self.content


def _make_deliver_processor(monkeypatch: pytest.MonkeyPatch, formatted_text: str) -> Any:
    """构造调用 _deliver_message 需要的最小 processor"""
    import nonebot_plugin_chat.core.processor as module
    from nonebot_plugin_chat.core.processor import MessageProcessor

    _FakeUniMessage.instances.clear()
    monkeypatch.setattr(module, "UniMessage", _FakeUniMessage)
    monkeypatch.setattr(module, "QQBot", _FakeQQBot)
    processor = MessageProcessor.__new__(MessageProcessor)
    processor.session = SimpleNamespace(
        format_message=AsyncMock(return_value=_FakeUniMessage(formatted_text)),
        target=None,
        bot=_FakeQQBot(),
        on_cache_posted=AsyncMock(),
        last_activate=None,
    )
    processor.consecutive_message_count = 0
    processor.unanalyzed_message_count = 0
    processor.openai_messages = SimpleNamespace(append_assistant_message=AsyncMock())
    processor._record_reply_timing = lambda *args, **kwargs: None
    return processor


async def test_deliver_message_sends_markdown_with_suggestion_buttons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """QQ 平台下最后一条消息以 markdown 发送，并附带备选回复按钮"""
    import nonebot_plugin_chat.core.processor as module

    processor = _make_deliver_processor(monkeypatch, "你好.喵")
    monkeypatch.setattr(module, "QQBot", _FakeQQBot)

    sent_msg_id = await processor._deliver_message(
        "你好.喵",
        "reply-id",
        0,
        markdown=True,
        suggestions=["选项一", "选项二"],
    )

    sent = _FakeUniMessage.instances[-1]
    assert sent_msg_id == "mid-1"
    assert sent.styles == ["markdown"]
    assert "\\." in sent.content
    assert [button.label for button in sent.buttons] == ["选项一", "选项二"]
    assert [button.text for button in sent.buttons] == ["选项一", "选项二"]
    # markdown 消息不附带引用
    assert sent.reply_id is None
    sent.send.assert_awaited_once()
    processor.openai_messages.append_assistant_message.assert_awaited_once()


async def test_deliver_message_keeps_plain_message_for_other_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非 QQ 平台不支持按钮：最后一条消息按普通消息发送，不套 markdown"""
    import nonebot_plugin_chat.core.processor as module

    processor = _make_deliver_processor(monkeypatch, "你好喵")
    monkeypatch.setattr(module, "QQBot", type("NotQQBot", (), {}))

    await processor._deliver_message("你好喵", None, 0, markdown=True, suggestions=["选项一"])

    sent = _FakeUniMessage.instances[0]
    assert sent.styles == []
    assert sent.buttons == []
    sent.send.assert_awaited_once()


async def test_button_label_is_truncated_for_long_suggestions() -> None:
    """按钮 label 过长时截断，但回传文本保持完整"""
    from nonebot_plugin_chat.core.processor import MessageProcessor

    long_reply = "这是一条非常长的备选回复" * 3

    assert MessageProcessor._button_label(long_reply) == f"{long_reply[:19]}…"
    assert MessageProcessor._button_label("短回复") == "短回复"
