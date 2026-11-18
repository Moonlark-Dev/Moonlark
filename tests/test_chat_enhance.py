"""群聊回复增强（``/chat enhance``）的回归测试

覆盖开关判定（群聊 + OpenAI Provider）、重写结果清洗与失败回落、重写上下文包含
Chat 的 System Prompt 与最近 5 条消息，以及 ``send_message`` 发送重写后的内容
并把重写结果写回工具结果。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


class _FinishedError(Exception):
    """模拟 lang.finish 的终止语义"""

    def __init__(self, key: str, args: tuple[Any, ...] = ()) -> None:
        super().__init__(key)
        self.key = key
        self.args = args


class _FakeDBSession:
    """只实现 ``async with get_session() as db`` 与 ``get`` 的假数据库会话"""

    def __init__(self, config: Any) -> None:
        self.config = config

    async def __aenter__(self) -> "_FakeDBSession":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    async def get(self, model: Any, key: Any) -> Any:
        return self.config


def _make_enhancer(
    *,
    session_type: str = "group",
    cached: str = "",
    system_content: Any = "CHAT SYSTEM",
) -> tuple[Any, Any]:
    """构造一个最小可用的 ReplyEnhancer 与被它持有的 processor"""
    from nonebot_plugin_chat.core.enhance import ReplyEnhancer

    session = SimpleNamespace(
        session_id="qq_10000",
        get_session_type=lambda: session_type,
        get_cached_messages_string=AsyncMock(return_value=cached),
    )
    processor = SimpleNamespace(
        session=session,
        generate_system_prompt=AsyncMock(return_value={"role": "system", "content": system_content}),
    )
    return ReplyEnhancer(processor), processor


def _patch_finish(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[Any, ...]]]:
    from nonebot_plugin_chat.matcher import chat

    calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fake_finish(key: str, _user_id: str, *args: Any, **_kwargs: Any) -> None:
        calls.append((key, args))
        raise _FinishedError(key, args)

    monkeypatch.setattr(chat.lang, "finish", fake_finish)
    return calls


def _make_handler(text: str) -> Any:
    from nonebot.adapters.onebot.v11 import Message
    from nonebot_plugin_chat.matcher.chat import CommandHandler

    return CommandHandler(MagicMock(), MagicMock(), MagicMock(), Message(text), MagicMock(), "10000", "10")


# ---------------------------------------------------------------------------
# 开关判定
# ---------------------------------------------------------------------------


async def test_is_enabled_requires_group_openai_and_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """只有「群聊 + 开关打开 + openai provider」三者同时满足才启用"""
    from nonebot_plugin_chat.core import enhance as module

    enhancer, _ = _make_enhancer()
    provider = AsyncMock(return_value="openai")
    monkeypatch.setattr(module, "get_model_provider", provider)
    monkeypatch.setattr(module, "get_session", lambda: _FakeDBSession(SimpleNamespace(enhance=True)))
    assert await enhancer.is_enabled()

    # 使用 Gemini Provider 时回复增强不生效
    provider.return_value = "gemini"
    assert not await enhancer.is_enabled()

    # 开关关闭
    provider.return_value = "openai"
    monkeypatch.setattr(module, "get_session", lambda: _FakeDBSession(SimpleNamespace(enhance=False)))
    assert not await enhancer.is_enabled()

    # 群聊没有配置记录
    monkeypatch.setattr(module, "get_session", lambda: _FakeDBSession(None))
    assert not await enhancer.is_enabled()

    # 私聊恒为关闭
    monkeypatch.setattr(module, "get_session", lambda: _FakeDBSession(SimpleNamespace(enhance=True)))
    private_enhancer, _ = _make_enhancer(session_type="private")
    assert not await private_enhancer.is_enabled()


async def test_is_enabled_swallows_database_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """读取开关失败时按未开启处理，不能把异常抛给 send_message"""
    from nonebot_plugin_chat.core import enhance as module

    enhancer, _ = _make_enhancer()

    def broken_session() -> Any:
        raise RuntimeError("数据库不可用")

    monkeypatch.setattr(module, "get_session", broken_session)
    monkeypatch.setattr(module, "get_model_provider", AsyncMock(return_value="openai"))

    assert not await enhancer.is_enabled()


# ---------------------------------------------------------------------------
# 重写与清洗
# ---------------------------------------------------------------------------


async def test_process_only_rewrites_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """关闭时原样返回；开启时返回重写结果并标记被重写"""
    enhancer, _ = _make_enhancer()
    enhancer.is_enabled = AsyncMock(return_value=False)
    enhancer.rewrite = AsyncMock(return_value="不该用到")
    assert await enhancer.process("原消息") == ("原消息", False)
    enhancer.rewrite.assert_not_awaited()

    enhancer.is_enabled = AsyncMock(return_value=True)
    enhancer.rewrite = AsyncMock(return_value="重写后的消息")
    assert await enhancer.process("原消息") == ("重写后的消息", True)

    # 重写结果与原文一致时不标记为被重写
    enhancer.rewrite = AsyncMock(return_value="原消息")
    assert await enhancer.process("原消息") == ("原消息", False)


async def test_process_skips_empty_content() -> None:
    """空消息不调用重写"""
    enhancer, _ = _make_enhancer()
    enhancer.is_enabled = AsyncMock(return_value=True)
    enhancer.rewrite = AsyncMock(return_value="重写后的消息")

    assert await enhancer.process("   ") == ("   ", False)
    enhancer.rewrite.assert_not_awaited()


def test_sanitize_strips_fences_quotes_and_truncates() -> None:
    """模型输出可能带代码块、引号或超长内容，都要清洗"""
    from nonebot_plugin_chat.core.enhance import MAX_REWRITTEN_LENGTH, ReplyEnhancer

    assert ReplyEnhancer._sanitize("```text\n你好呀.喵\n```") == "你好呀.喵"
    assert ReplyEnhancer._sanitize('  "你好呀"  ') == "你好呀"
    assert ReplyEnhancer._sanitize("“你好呀”") == "你好呀"
    assert ReplyEnhancer._sanitize("   ") == ""
    assert ReplyEnhancer._sanitize("x" * (MAX_REWRITTEN_LENGTH + 50)) == "x" * MAX_REWRITTEN_LENGTH


async def test_rewrite_uses_chat_prompt_and_recent_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    """重写请求的上下文包含 Chat 的 System Prompt、最近对话与待发送内容"""
    from nonebot_plugin_chat.core import enhance as module

    fetch = AsyncMock(return_value="重写后的消息")
    monkeypatch.setattr(module, "fetch_message", fetch)
    enhancer, processor = _make_enhancer(cached="[12:00:00][小明]: 在吗")

    assert await enhancer.rewrite("你好呀") == "重写后的消息"

    processor.session.get_cached_messages_string.assert_awaited_once()
    messages = fetch.await_args.args[0]
    system_text = messages[0]["content"]
    user_text = messages[1]["content"]
    assert "CHAT SYSTEM" in system_text
    assert "重写" in system_text
    assert "[12:00:00][小明]: 在吗" in user_text
    assert "你好呀" in user_text
    assert fetch.await_args.kwargs["identify"] == "Chat Enhance - Rewrite Message"


async def test_rewrite_supports_multimodal_system_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """System Prompt 的 content 是分段列表时也要取出文本"""
    from nonebot_plugin_chat.core import enhance as module

    fetch = AsyncMock(return_value="重写后的消息")
    monkeypatch.setattr(module, "fetch_message", fetch)
    enhancer, _ = _make_enhancer(
        system_content=[{"type": "text", "text": "CHAT SYSTEM"}],
    )

    await enhancer.rewrite("你好呀")

    assert "CHAT SYSTEM" in fetch.await_args.args[0][0]["content"]


async def test_rewrite_falls_back_to_original(monkeypatch: pytest.MonkeyPatch) -> None:
    """重写失败或结果为空时发送原文，不把异常抛给调用方"""
    from nonebot_plugin_chat.core import enhance as module

    enhancer, _ = _make_enhancer()
    monkeypatch.setattr(module, "fetch_message", AsyncMock(side_effect=RuntimeError("LLM 不可用")))
    assert await enhancer.rewrite("原消息") == "原消息"

    monkeypatch.setattr(module, "fetch_message", AsyncMock(return_value="   "))
    assert await enhancer.rewrite("原消息") == "原消息"


# ---------------------------------------------------------------------------
# send_message 集成
# ---------------------------------------------------------------------------


def _make_send_processor(enhanced_result: tuple[str, bool], sent: list[tuple[str, tuple[Any, ...]]]) -> Any:
    """构造调用 ``MessageProcessor.send_message`` 需要的最小 processor"""
    from nonebot_plugin_chat.core.processor import MessageProcessor

    processor = MessageProcessor.__new__(MessageProcessor)

    async def fake_text(key: str, *args: Any) -> str:
        sent.append((key, args))
        if key == "message.sent":
            return f"SENT|{args[0]}"
        if key == "message.enhanced":
            return f"ENHANCED|{args[0]}"
        return key

    processor.session = SimpleNamespace(
        session_id="qq_10000",
        get_session_type=lambda: "group",
        text=fake_text,
    )
    processor.enhancer = SimpleNamespace(process=AsyncMock(return_value=enhanced_result))
    processor.gal_mode = SimpleNamespace(should_buffer=lambda: False)
    processor.token_bucket = SimpleNamespace(get=lambda: 10, consume=lambda count: None)
    processor.unlimited_tokens_active = False
    processor.important_turn_quota = False
    processor.consecutive_message_count = 0
    processor._deliver_message = AsyncMock(return_value="msg-id")
    processor._format_pending_notes_for_tool_result = lambda: ""
    return processor


async def test_send_message_sends_rewritten_content_and_reports_it() -> None:
    """``send_message`` 发送重写后的内容，并把重写结果写回工具结果"""
    from nonebot_plugin_chat.core.processor import MessageProcessor

    sent: list[tuple[str, tuple[Any, ...]]] = []
    processor = _make_send_processor(("重写后的消息", True), sent)

    result = await MessageProcessor.send_message(processor, "原始消息")

    processor._deliver_message.assert_awaited_once()
    assert processor._deliver_message.await_args.args[0] == "重写后的消息"
    assert "SENT|msg-id" in result
    assert "ENHANCED|重写后的消息" in result
    assert ("message.enhanced", ("重写后的消息",)) in sent


async def test_send_message_omits_enhance_note_when_not_rewritten() -> None:
    """没有发生重写时工具结果里不额外说明实际发送内容"""
    from nonebot_plugin_chat.core.processor import MessageProcessor

    sent: list[tuple[str, tuple[Any, ...]]] = []
    processor = _make_send_processor(("原始消息", False), sent)

    result = await MessageProcessor.send_message(processor, "原始消息")

    assert processor._deliver_message.await_args.args[0] == "原始消息"
    assert "ENHANCED" not in result
    assert all(key != "message.enhanced" for key, _ in sent)


async def test_send_message_without_enhancer_attribute_still_works() -> None:
    """老测试/精简对象没有 enhancer 属性时照常发送（钩子必须防御性取值）"""
    from nonebot_plugin_chat.core.processor import MessageProcessor

    sent: list[tuple[str, tuple[Any, ...]]] = []

    async def fake_text(key: str, *args: Any) -> str:
        sent.append((key, args))
        return key

    processor = MessageProcessor.__new__(MessageProcessor)
    processor.session = SimpleNamespace(get_session_type=lambda: "group", text=fake_text, session_id="qq_10000")
    processor.gal_mode = SimpleNamespace(should_buffer=lambda: False)
    processor.token_bucket = SimpleNamespace(get=lambda: 10, consume=lambda count: None)
    processor.unlimited_tokens_active = False
    processor.important_turn_quota = False
    processor.consecutive_message_count = 0
    processor._deliver_message = AsyncMock(return_value="msg-id")
    processor._format_pending_notes_for_tool_result = lambda: ""

    await MessageProcessor.send_message(processor, "原始消息")

    processor._deliver_message.assert_awaited_once()
    assert processor._deliver_message.await_args.args[0] == "原始消息"


# ---------------------------------------------------------------------------
# /chat enhance 命令
# ---------------------------------------------------------------------------


async def test_enhance_command_persists_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """``/chat enhance on|off`` 写入 ChatGroup.enhance"""
    from nonebot_plugin_chat.matcher import chat

    calls = _patch_finish(monkeypatch)
    monkeypatch.setattr(chat, "get_model_provider", AsyncMock(return_value="openai"))

    handler = _make_handler("enhance on")
    handler.is_private_chat = False
    handler.group_config = SimpleNamespace(enhance=False)
    handler.merge_group_config = AsyncMock()

    with pytest.raises(_FinishedError):
        await handler.handle_enhance()

    assert handler.group_config.enhance is True
    handler.merge_group_config.assert_awaited_once()
    assert calls == [("command.enhance.enabled", ())]

    handler = _make_handler("enhance off")
    handler.is_private_chat = False
    handler.group_config = SimpleNamespace(enhance=True)
    handler.merge_group_config = AsyncMock()

    with pytest.raises(_FinishedError):
        await handler.handle_enhance()

    assert handler.group_config.enhance is False
    handler.merge_group_config.assert_awaited_once()
    assert calls[-1] == ("command.enhance.disabled", ())


async def test_enhance_command_reports_current_state_without_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    """不带参数时只回报当前状态，不写库"""
    calls = _patch_finish(monkeypatch)

    on_handler = _make_handler("enhance")
    on_handler.is_private_chat = False
    on_handler.group_config = SimpleNamespace(enhance=True)
    on_handler.merge_group_config = AsyncMock()

    with pytest.raises(_FinishedError):
        await on_handler.handle_enhance()

    on_handler.merge_group_config.assert_not_awaited()
    assert calls[-1][0] == "command.enhance.current_on"

    off_handler = _make_handler("enhance")
    off_handler.is_private_chat = False
    off_handler.group_config = SimpleNamespace(enhance=False)
    off_handler.merge_group_config = AsyncMock()

    with pytest.raises(_FinishedError):
        await off_handler.handle_enhance()

    off_handler.merge_group_config.assert_not_awaited()
    assert calls[-1][0] == "command.enhance.current_off"


async def test_enhance_command_warns_when_provider_is_not_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    """开启时若当前不是 OpenAI Provider，提示回复增强不会生效"""
    from nonebot_plugin_chat.matcher import chat

    calls = _patch_finish(monkeypatch)
    monkeypatch.setattr(chat, "get_model_provider", AsyncMock(return_value="gemini"))

    handler = _make_handler("enhance on")
    handler.is_private_chat = False
    handler.group_config = SimpleNamespace(enhance=False)
    handler.merge_group_config = AsyncMock()

    with pytest.raises(_FinishedError):
        await handler.handle_enhance()

    assert handler.group_config.enhance is True
    assert calls == [("command.enhance.enabled_provider_warning", ("gemini",))]


async def test_private_chat_enhance_reports_group_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """私聊中 ``/chat enhance`` 提示仅群聊可用，不能落到 private_only_switch"""
    calls = _patch_finish(monkeypatch)

    handler = _make_handler("enhance on")
    handler.is_private_chat = True
    handler.group_config = SimpleNamespace(enhance=False)
    handler.merge_group_config = AsyncMock()

    with pytest.raises(_FinishedError):
        await handler.handle()

    assert calls == [("command.enhance.group_only", ())]
    handler.merge_group_config.assert_not_awaited()


# ---------------------------------------------------------------------------
# 提示词模板
# ---------------------------------------------------------------------------


async def test_enhance_prompt_renders_expected_inputs() -> None:
    """重写提示词包含任务说明、最近对话与待发送内容"""
    from nonebot_plugin_openai.utils.message import get_message_text

    system = await get_message_text("chat_enhance/system.md.jinja")
    user = await get_message_text(
        "chat_enhance/user.md.jinja",
        recent_messages="[12:00:00][小明]: 在吗",
        draft="你好呀",
    )

    assert "重写" in system
    assert "只输出" in system
    assert "最近的对话" in user
    assert "[12:00:00][小明]: 在吗" in user
    assert "你好呀" in user
