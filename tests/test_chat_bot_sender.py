"""QQ 官方适配器群消息里机器人发送者的处理。

需求：从群聊事件里读到发送者 ``is_bot``（适配器结构字段名为 ``bot``）为 ``True`` 时，

- 仍把消息放进上下文，但在 additional_info 中标注发送者是机器人；
- 该消息绝不触发回复（包括 @ 了 Moonlark 与冷群自动接话两条路径）；
- 机器人发言不计入触发概率的累计文本长度。
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _qq_group_event(bot: bool) -> Any:
    from nonebot.adapters.qq.event import GroupAtMessageCreateEvent

    return GroupAtMessageCreateEvent(
        id="msg-1",
        content="我是另一个机器人",
        timestamp="1700000000",
        group_id="group-id-1",
        group_openid="GROUP_OPENID_1",
        author={
            "id": "MEMBER_OPENID_1",
            "bot": bot,
            "member_openid": "MEMBER_OPENID_1",
            "member_role": "member",
            "username": "tester",
        },
    )


def _ob11_group_event() -> Any:
    from nonebot.adapters.onebot.v11.event import GroupMessageEvent, Sender

    return GroupMessageEvent(
        time=1700000000,
        self_id=123,
        post_type="message",
        message_type="group",
        sub_type="normal",
        message_id=1,
        group_id=701257458,
        user_id=10001,
        raw_message="我是另一个机器人",
        font=0,
        sender=Sender(user_id=10001, nickname="tester"),
        message=[{"type": "text", "data": {"text": "我是另一个机器人"}}],
    )


# --- is_bot_sender ---


def test_qq_group_bot_author_is_bot_sender() -> None:
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_chat.utils.bot_sender import is_bot_sender

    assert is_bot_sender(_qq_group_event(True), MagicMock(spec=QQBot)) is True


def test_qq_group_human_author_is_not_bot_sender() -> None:
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_chat.utils.bot_sender import is_bot_sender

    assert is_bot_sender(_qq_group_event(False), MagicMock(spec=QQBot)) is False


def test_non_qq_adapter_is_not_bot_sender() -> None:
    """只有 QQ 官方适配器提供发送者机器人标记，其它适配器一律按真人处理"""
    from nonebot.adapters.onebot.v11 import Bot as OB11Bot
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_chat.utils.bot_sender import is_bot_sender

    assert is_bot_sender(_qq_group_event(True), MagicMock(spec=OB11Bot)) is False
    assert is_bot_sender(_ob11_group_event(), MagicMock(spec=OB11Bot)) is False
    # 即使是 QQ 的 Bot，非群消息事件（例如 C2C）也没有作者 bot 标记
    assert is_bot_sender(_ob11_group_event(), MagicMock(spec=QQBot)) is False


# --- additional_info 标注 ---


async def test_additional_info_marks_bot_sender() -> None:
    from nonebot_plugin_openai.utils.message import get_message_text

    text = await get_message_text(
        "chat_message.md.jinja",
        nickname="机器人甲",
        display_fav=0,
        fav_level=0,
        note_text="暂无",
        tiredness=0,
        state="",
        sender_is_bot=True,
    )
    assert "机器人账号（bot）" in text


async def test_additional_info_does_not_mark_human_sender() -> None:
    from nonebot_plugin_openai.utils.message import get_message_text

    text = await get_message_text(
        "chat_message.md.jinja",
        nickname="小明",
        display_fav=0,
        fav_level=0,
        note_text="暂无",
        tiredness=0,
        state="",
        sender_is_bot=False,
    )
    assert "机器人账号（bot）" not in text


# --- 出队时的触发判定 ---


def _processor_with_message(event: Any, bot: Any, mentioned: bool) -> Any:
    from nonebot_plugin_chat.core.session.base import SessionQueue

    session = SimpleNamespace(
        message_queue=SessionQueue(lambda: None),
        bot=bot,
        get_session_type=lambda: "group",
        on_cache_posted=AsyncMock(),
    )
    session.message_queue.append(
        (
            "message",
            (object(), event, {}, "user-1", "小明", datetime.now(), mentioned, "msg-1", "user-1"),
        ),
    )
    return SimpleNamespace(
        session=session,
        consecutive_message_count=0,
        should_ignore_mention=AsyncMock(return_value=False),
        parse_message=AsyncMock(return_value=("大家好", [], [])),
        process_messages=AsyncMock(),
        token_bucket=SimpleNamespace(add=MagicMock()),
        blocked=False,
        generate_reply=AsyncMock(),
    )


async def test_bot_message_never_triggers_reply_even_when_mentioned() -> None:
    import importlib

    from nonebot.adapters.qq import Bot as QQBot

    processor_module = importlib.import_module("nonebot_plugin_chat.core.processor")
    processor = _processor_with_message(_qq_group_event(True), MagicMock(spec=QQBot), mentioned=True)

    await processor_module.MessageProcessor.get_message(processor)
    await asyncio.sleep(0)

    msg_dict, trigger_mode = processor.process_messages.await_args.args
    assert trigger_mode == "none"
    assert msg_dict["is_bot"] is True
    processor.token_bucket.add.assert_called_once_with(0.0)
    processor.generate_reply.assert_not_awaited()


async def test_human_message_still_triggers_by_probability() -> None:
    import importlib

    from nonebot.adapters.qq import Bot as QQBot

    processor_module = importlib.import_module("nonebot_plugin_chat.core.processor")
    processor = _processor_with_message(_qq_group_event(False), MagicMock(spec=QQBot), mentioned=True)

    await processor_module.MessageProcessor.get_message(processor)
    await asyncio.sleep(0)

    msg_dict, trigger_mode = processor.process_messages.await_args.args
    assert trigger_mode == "all"
    assert msg_dict["is_bot"] is False
    processor.generate_reply.assert_awaited_once()


# --- 冷群自动接话不把机器人发言当作最后一条真人消息 ---


@pytest.mark.parametrize(("last_message_is_bot", "expect_reply"), [(True, False), (False, True)])
async def test_cold_group_ignores_bot_last_message(
    monkeypatch: pytest.MonkeyPatch, last_message_is_bot: bool, expect_reply: bool
) -> None:
    import importlib

    from nonebot_plugin_chat.core.session.base import BaseSession, SessionQueue
    from nonebot_plugin_chat.core.session.group import GroupSession

    group_module = importlib.import_module("nonebot_plugin_chat.core.session.group")
    cached = [
        {
            "content": "我是另一个机器人",
            "nickname": "机器人甲",
            "user_id": "user-1",
            "platform_user_id": "user-1",
            "send_time": datetime.now() - timedelta(hours=1),
            "images": [],
            "self": False,
            "message_id": "msg-1",
            "to_me": False,
            "triggered_reply": False,
            "is_bot": last_message_is_bot,
        }
    ]
    processor = SimpleNamespace(
        blocked=False,
        openai_messages=SimpleNamespace(
            _ensure_system_prompt=AsyncMock(),
            context=SimpleNamespace(cached_messages=cached),
        ),
        token_bucket=SimpleNamespace(add=MagicMock()),
        generate_reply=AsyncMock(),
    )
    session = GroupSession.__new__(GroupSession)
    session.session_id = "pytest_cold_group"
    session.processor = processor
    session.message_queue = SessionQueue(lambda: None)
    session.cached_latest_message = None

    monkeypatch.setattr(BaseSession, "process_timer", AsyncMock())
    monkeypatch.setattr(group_module, "get_group_hot_score", AsyncMock(return_value=(0, 0, 10)))

    await session.process_timer()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    if expect_reply:
        processor.generate_reply.assert_awaited_once()
        assert session.cached_latest_message is cached[-1]
    else:
        processor.generate_reply.assert_not_awaited()
        assert session.cached_latest_message is None


# --- 机器人发言不计入累计文本长度 ---


@asynccontextmanager
async def _fake_db_session():
    yield SimpleNamespace(get=AsyncMock(return_value=None))


def _process_messages_processor() -> Any:
    return SimpleNamespace(
        session=SimpleNamespace(session_id="pytest_bot_sender_group", accumulated_text_length=0),
        openai_messages=SimpleNamespace(append_user_message_with_data=AsyncMock()),
        blocked=False,
        generate_additional_prompt=AsyncMock(return_value="[additional_info]"),
        build_message_content=lambda msg_str, images: [{"type": "text", "text": msg_str}],
        _get_pending_notes_text=lambda: "",
    )


def _cached_message(is_bot: bool) -> Any:
    return {
        "content": "这是机器人说的话，长度不算短，用来验证累计文本长度",
        "nickname": "机器人甲" if is_bot else "小明",
        "user_id": "user-1",
        "platform_user_id": "user-1",
        "send_time": datetime.now(),
        "images": [],
        "self": False,
        "message_id": "msg-1",
        "to_me": False,
        "triggered_reply": False,
        "is_bot": is_bot,
    }


async def test_bot_message_text_not_accumulated() -> None:
    import importlib

    processor_module = importlib.import_module("nonebot_plugin_chat.core.processor")
    processor = _process_messages_processor()

    with patch.object(processor_module, "get_session", _fake_db_session):
        await processor_module.MessageProcessor.process_messages(processor, _cached_message(True), "none")

    assert processor.session.accumulated_text_length == 0
    assert processor.generate_additional_prompt.await_args.kwargs["sender_is_bot"] is True


async def test_human_message_text_is_accumulated() -> None:
    import importlib

    processor_module = importlib.import_module("nonebot_plugin_chat.core.processor")
    processor = _process_messages_processor()

    with patch.object(processor_module, "get_session", _fake_db_session):
        await processor_module.MessageProcessor.process_messages(processor, _cached_message(False), "probability")

    assert processor.session.accumulated_text_length > 0
    assert processor.generate_additional_prompt.await_args.kwargs["sender_is_bot"] is False
