"""主动私聊必须使用主动消息发送

会话已初始化时 ``create_private_session`` 会复用旧会话及其旧 target：旧 target 的
``source`` 是上一次被动回复的消息 id。QQ 官方适配器发送 C2C 时会把 ``source`` 当作
``msg_id``，主动私聊再用这个已经过期的 id 就会触发 40034005。主动私聊必须换用不带
``source`` 的 target，让适配器走主动消息。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch


def test_build_proactive_target_has_no_source() -> None:
    """主动私聊 Target 不带 source，QQ 适配器才会按主动消息发送"""
    from nonebot_plugin_chat.core.proactive_chat import build_proactive_target
    from nonebot_plugin_chat.models import PrivateChatSession

    chat_session = PrivateChatSession(
        user_id="3889000000",
        session_key="qq_friend_openid",
        bot_id="102000000",
        adapter_name="QQ",
        platform_user_id="user_openid",
    )

    target = build_proactive_target(chat_session, "QQ")

    assert target.id == "user_openid"
    assert target.private is True
    assert target.source == ""
    assert target.extra["adapter"] == "QQ"


async def test_proactive_send_refreshes_stale_session_target() -> None:
    """已初始化的会话被复用时，主动私聊要把 target 换成主动消息 target"""
    from nonebot_plugin_chat.core import proactive_chat

    chat_session = SimpleNamespace(
        user_id="3889000000",
        session_key="qq_friend_openid",
        bot_id="102000000",
        adapter_name="QQ",
        platform_user_id="user_openid",
    )
    stale_target = SimpleNamespace(source="expired_message_id")

    class FakeSession:
        def __init__(self) -> None:
            self.target: Any = stale_target
            self.bot: Any = None
            self.events: list[tuple[str, str]] = []

        def set_target(self, target: Any, bot: Any) -> None:
            self.target = target
            self.bot = bot

        async def post_event(self, prompt: str, trigger_mode: str) -> None:
            self.events.append((prompt, trigger_mode))

    fake_session = FakeSession()
    bot = SimpleNamespace(adapter=SimpleNamespace(get_name=lambda: "QQ"))
    result = SimpleNamespace(scalar_one_or_none=lambda: chat_session)
    fake_db_session = SimpleNamespace(execute=AsyncMock(return_value=result))
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = fake_db_session
    record_mock = AsyncMock()

    with (
        patch.object(proactive_chat, "get_session", return_value=session_cm),
        patch.object(
            proactive_chat,
            "create_private_session",
            AsyncMock(return_value=fake_session),
        ),
        patch.object(proactive_chat, "lang", SimpleNamespace(text=AsyncMock(return_value="prompt"))),
        patch.object(
            proactive_chat,
            "get_user",
            AsyncMock(return_value=SimpleNamespace(get_nickname=lambda: "昵称")),
        ),
        patch.object(proactive_chat, "record_proactive_message", record_mock),
    ):
        await proactive_chat.send_proactive_private_message(bot, chat_session.user_id, "topic")

    assert fake_session.target is not stale_target
    assert fake_session.target.source == ""
    assert fake_session.target.id == "user_openid"
    assert fake_session.bot is bot
    assert fake_session.events == [("prompt", "all")]
    record_mock.assert_awaited_once()
