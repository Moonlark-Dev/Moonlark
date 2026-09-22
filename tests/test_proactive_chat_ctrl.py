"""主动私聊控制器测试：分级冷却与连续未回复限制"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.parametrize(
    ("favorability", "expected"),
    [
        (0.5, 24.0),
        (0.301, 24.0),
        (0.3, 48.0),
        (0.151, 48.0),
        (0.15, 72.0),
        (0.051, 72.0),
        (0.05, float("inf")),
        (0.0, float("inf")),
        (-0.1, float("inf")),
    ],
)
def test_get_cooldown_hours(favorability: float, expected: float) -> None:
    from nonebot_plugin_chat.core.ego.proactive_chat_ctrl import get_cooldown_hours

    assert get_cooldown_hours(favorability) == expected


async def test_get_candidates_filters_ineligible() -> None:
    from nonebot_plugin_chat.core.ego import proactive_chat_ctrl as ctrl
    from nonebot_plugin_chat.models import PrivateChatSession

    now = datetime.now(timezone.utc).timestamp()
    # (user_id, nickname, fav, last_proactive_message_time, unreplied_count, 是否应入选)
    cases = [
        ("u_fav_low", "低好感", 0.04, None, 0, False),  # 好感度过低，不允许主动私聊
        ("u_cooling", "冷却中", 0.5, now - 12 * 3600, 0, False),  # 24h 冷却期内（12h 前）→ 排除
        ("u_cool_ok", "冷却过", 0.5, now - 25 * 3600, 0, True),  # 超过 24h 冷却 → 入选
        ("u_unreplied2", "未回复x2", 0.6, now - 48 * 3600, 2, False),  # 连续 2 次未回复 → 排除
        ("u_unreplied1", "未回复x1", 0.6, now - 48 * 3600, 1, True),  # 1 次未回复 → 入选
        ("u_never", "从未私聊", 0.8, None, 0, True),  # 无主动私聊记录 → 入选
    ]

    sessions = []
    for user_id, _, _, last_proactive, unreplied, _ in cases:
        session = PrivateChatSession(
            user_id=user_id,
            session_key=f"qq_{user_id}",
            bot_id="bot1",
            last_message_time=now,
            last_proactive_message_time=last_proactive,
            unreplied_count=unreplied,
        )
        sessions.append(session)

    fake_scalars = SimpleNamespace(all=lambda: sessions)
    fake_result = SimpleNamespace(scalars=lambda: fake_scalars)
    fake_db_session = SimpleNamespace(execute=AsyncMock(return_value=fake_result))
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = fake_db_session

    def fake_get_user(user_id: str):
        info = next(c for c in cases if c[0] == user_id)
        return SimpleNamespace(
            get_nickname=lambda: info[1],
            get_display_fav=lambda: info[2],
        )

    with (
        patch.object(ctrl, "get_session", return_value=session_cm),
        patch.object(ctrl, "get_available_bot_ids", AsyncMock(return_value={"bot1"})),
        patch("nonebot_plugin_larkuser.utils.user.get_user", side_effect=fake_get_user),
    ):
        controller = ctrl.ProactiveChatController(moonlark_main=None)  # type: ignore[arg-type]
        candidates = await controller._get_candidates()  # noqa: SLF001

    expected_ids = {c[0] for c in cases if c[5]}
    assert set(candidates) == expected_ids
    for user_id in expected_ids:
        assert candidates[user_id]["nickname"] == next(c[1] for c in cases if c[0] == user_id)


def _fake_session_ctx(sessions: list) -> AsyncMock:
    """构造返回指定私聊会话列表的 get_session 上下文"""
    fake_scalars = SimpleNamespace(all=lambda: sessions)
    fake_result = SimpleNamespace(scalars=lambda: fake_scalars)
    fake_db_session = SimpleNamespace(execute=AsyncMock(return_value=fake_result))
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = fake_db_session
    return session_cm


def _make_session(user_id: str, bot_id: str) -> object:
    from nonebot_plugin_chat.models import PrivateChatSession

    return PrivateChatSession(
        user_id=user_id,
        session_key=f"qq_{user_id}",
        bot_id=bot_id,
        last_message_time=0.0,
        unreplied_count=0,
    )


async def _collect_candidates(
    ctrl: object,
    sessions: list,
    available_bots: set[str] | None,
    users: dict[str, object],
) -> tuple[dict[str, dict], object]:
    """运行 _get_candidates，返回 (候选列表, 控制器)"""
    with (
        patch.object(ctrl, "get_session", return_value=_fake_session_ctx(sessions)),
        patch.object(ctrl, "get_available_bot_ids", AsyncMock(return_value=available_bots)),
        patch("nonebot_plugin_larkuser.utils.user.get_user", side_effect=lambda user_id: users[user_id]),
    ):
        controller = ctrl.ProactiveChatController(moonlark_main=None)  # type: ignore[arg-type]
        candidates = await controller._get_candidates()  # noqa: SLF001
    return candidates, controller


async def test_get_candidates_skips_users_whose_bot_is_unavailable() -> None:
    """bot 离线/状态异常的用户不作为主动私聊候选，并记录到决策历史"""
    from nonebot_plugin_chat.core.ego import proactive_chat_ctrl as ctrl

    sessions = [_make_session("u_online", "bot_online"), _make_session("u_offline", "bot_offline")]
    users = {
        "u_online": SimpleNamespace(get_nickname=lambda: "在线用户", get_display_fav=lambda: 0.5),
        "u_offline": SimpleNamespace(get_nickname=lambda: "离线用户", get_display_fav=lambda: 0.5),
    }

    candidates, controller = await _collect_candidates(ctrl, sessions, {"bot_online"}, users)

    assert set(candidates) == {"u_online"}
    unavailable_records = [
        r for r in controller.decision_history if r.get("stage") == "bot_unavailable"
    ]  # noqa: SLF001
    assert [r["users"] for r in unavailable_records] == [["u_offline"]]


async def test_get_candidates_without_bot_status_does_not_filter() -> None:
    """无法判断 bot 状态时（返回 None）不按 bot 可用性过滤"""
    from nonebot_plugin_chat.core.ego import proactive_chat_ctrl as ctrl

    sessions = [_make_session("u1", "bot1"), _make_session("u2", "bot2")]
    users = {
        "u1": SimpleNamespace(get_nickname=lambda: "用户1", get_display_fav=lambda: 0.5),
        "u2": SimpleNamespace(get_nickname=lambda: "用户2", get_display_fav=lambda: 0.5),
    }

    candidates, _ = await _collect_candidates(ctrl, sessions, None, users)

    assert set(candidates) == {"u1", "u2"}


async def test_send_proactive_prefers_session_with_available_bot() -> None:
    """同名用户存在多条记录时，跳过 bot 不可用的记录，发送到可用 bot 的记录"""
    from nonebot_plugin_chat.core.ego import proactive_chat_ctrl as ctrl

    offline = _make_session("u_openid", "bot_offline")
    online = _make_session("u_qq", "bot_online")
    users = {
        "u_openid": SimpleNamespace(get_nickname=lambda: "小明"),
        "u_qq": SimpleNamespace(get_nickname=lambda: "小明"),
    }
    sent = AsyncMock()
    bot = SimpleNamespace(self_id="bot_online")

    with (
        patch.object(ctrl, "get_session", return_value=_fake_session_ctx([offline, online])),
        patch.object(ctrl, "get_available_bot_ids", AsyncMock(return_value={"bot_online"})),
        patch("nonebot_plugin_larkuser.utils.user.get_user", side_effect=lambda user_id: users[user_id]),
        patch("nonebot.get_bot", return_value=bot),
        patch("nonebot_plugin_chat.core.proactive_chat.send_proactive_private_message", new=sent),
    ):
        controller = ctrl.ProactiveChatController(moonlark_main=None)  # type: ignore[arg-type]
        result = await controller._send_proactive(
            ctrl.ProactiveDecision(target_nickname="小明", topic="你好")
        )  # noqa: SLF001

    assert result == "已向 小明 发送主动私聊"
    sent.assert_awaited_once_with(bot, "u_qq", "你好")


async def test_send_proactive_reports_when_no_bot_available() -> None:
    """同名记录对应的 bot 都不可用时，不发送并返回可读原因"""
    from nonebot_plugin_chat.core.ego import proactive_chat_ctrl as ctrl

    session = _make_session("u1", "bot_offline")
    users = {"u1": SimpleNamespace(get_nickname=lambda: "小明")}
    sent = AsyncMock()

    with (
        patch.object(ctrl, "get_session", return_value=_fake_session_ctx([session])),
        patch.object(ctrl, "get_available_bot_ids", AsyncMock(return_value=set())),
        patch("nonebot_plugin_larkuser.utils.user.get_user", side_effect=lambda user_id: users[user_id]),
        patch("nonebot_plugin_chat.core.proactive_chat.send_proactive_private_message", new=sent),
    ):
        controller = ctrl.ProactiveChatController(moonlark_main=None)  # type: ignore[arg-type]
        result = await controller._send_proactive(
            ctrl.ProactiveDecision(target_nickname="小明", topic="你好")
        )  # noqa: SLF001

    assert result == "小明 没有可用的 bot 在线"
    sent.assert_not_awaited()


async def test_get_recent_sends_formats_history() -> None:
    from nonebot_plugin_chat.core.ego import proactive_chat_ctrl as ctrl

    # 数据库按发送时间倒序返回最近 N 条
    records = [
        SimpleNamespace(nickname="", user_id="u2", content="在吗", sent_at=datetime(2026, 9, 16, 10, 0)),
        SimpleNamespace(nickname="小明", user_id="u1", content="早上好", sent_at=datetime(2026, 9, 16, 9, 0)),
    ]
    fake_scalars = SimpleNamespace(all=lambda: records)
    fake_db_session = SimpleNamespace(scalars=AsyncMock(return_value=fake_scalars))
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = fake_db_session

    with patch.object(ctrl, "get_session", return_value=session_cm):
        controller = ctrl.ProactiveChatController(moonlark_main=None)  # type: ignore[arg-type]
        text = await controller._get_recent_sends()  # noqa: SLF001

    # 展示时恢复为时间正序，昵称为空时回退到 user_id
    assert text.splitlines() == [
        "- [09-16 09:00] 给 小明: 早上好",
        "- [09-16 10:00] 给 u2: 在吗",
    ]


async def test_get_recent_sends_empty() -> None:
    from nonebot_plugin_chat.core.ego import proactive_chat_ctrl as ctrl

    empty: list = []
    fake_db_session = SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: empty)))
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = fake_db_session

    with patch.object(ctrl, "get_session", return_value=session_cm):
        controller = ctrl.ProactiveChatController(moonlark_main=None)  # type: ignore[arg-type]
        text = await controller._get_recent_sends()  # noqa: SLF001

    assert text == "暂无主动私聊发送记录。"
