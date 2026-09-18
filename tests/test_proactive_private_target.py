"""主动私聊发送目标测试：按适配器选择正确的用户 ID

`PrivateChatSession.user_id` 是 Moonlark 主账号 ID：QQ 官方适配器的私聊经自动绑定后
会变成 QQ 号，但 QQ 官方适配器发送 C2C 消息需要 openid，因此发送时应使用记录里保存的
适配器原始 user_id（platform_user_id）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nonebot_plugin_chat.models import PrivateChatSession


def _make_session(adapter_name: str | None = None, platform_user_id: str | None = None) -> PrivateChatSession:
    from nonebot_plugin_chat.models import PrivateChatSession

    return PrivateChatSession(
        user_id="3889000000",
        session_key="qq_friend_openid",
        bot_id="102000000",
        adapter_name=adapter_name,
        platform_user_id=platform_user_id,
        last_message_time=0.0,
    )


def test_uses_platform_user_id_when_adapter_matches() -> None:
    """QQ 官方适配器：user_id 是绑定后的 QQ 号，必须用 openid 发送"""
    from nonebot_plugin_chat.core.proactive_chat import get_proactive_target_user_id

    session = _make_session(adapter_name="QQ", platform_user_id="user_openid")
    assert get_proactive_target_user_id(session, "QQ") == "user_openid"


def test_falls_back_to_user_id_for_legacy_record() -> None:
    """旧记录没有 adapter_name / platform_user_id，保持原有行为"""
    from nonebot_plugin_chat.core.proactive_chat import get_proactive_target_user_id

    session = _make_session()
    assert session.adapter_name is None
    assert session.platform_user_id is None
    assert get_proactive_target_user_id(session, "QQ") == "3889000000"


def test_falls_back_when_adapter_mismatch() -> None:
    """记录中的适配器与当前 bot 不一致时，不能把 openid 当作 OneBot 的 QQ 号发送"""
    from nonebot_plugin_chat.core.proactive_chat import get_proactive_target_user_id

    session = _make_session(adapter_name="QQ", platform_user_id="user_openid")
    assert get_proactive_target_user_id(session, "OneBot V11") == "3889000000"


def test_platform_user_id_without_adapter_name_falls_back() -> None:
    """只有 platform_user_id 而没有 adapter_name 时无法确认语义，回退到 user_id"""
    from nonebot_plugin_chat.core.proactive_chat import get_proactive_target_user_id

    session = _make_session(platform_user_id="user_openid")
    assert get_proactive_target_user_id(session, "QQ") == "3889000000"


def test_onebot_record_uses_platform_user_id() -> None:
    """OneBot 的 platform_user_id 就是 QQ 号，与 user_id 相同"""
    from nonebot_plugin_chat.core.proactive_chat import get_proactive_target_user_id

    session = _make_session(adapter_name="OneBot V11", platform_user_id="3889000000")
    assert get_proactive_target_user_id(session, "OneBot V11") == "3889000000"
