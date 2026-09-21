"""主动私聊控制器测试：分级冷却、用户静默期与连续未回复限制"""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
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


def test_is_user_recently_active() -> None:
    from nonebot_plugin_chat.core.ego import proactive_chat_ctrl as ctrl
    from nonebot_plugin_chat.models import PrivateChatSession

    now = datetime.now(timezone.utc).timestamp()
    # 1 小时前私聊过
    session = PrivateChatSession(user_id="u1", session_key="qq_u1", bot_id="bot1", last_message_time=now - 3600)

    with patch.object(ctrl.config, "proactive_chat_user_active_cooldown_hours", 12.0):
        assert ctrl.is_user_recently_active(session, now) is True
        # 12 小时前恰好达到静默期上限，不再视为“刚刚私聊过”
        assert ctrl.is_user_recently_active(session, now - 3600 + 12 * 3600) is False

    # 配置为 0 表示关闭该限制
    with patch.object(ctrl.config, "proactive_chat_user_active_cooldown_hours", 0.0):
        assert ctrl.is_user_recently_active(session, now) is False


async def test_get_candidates_filters_ineligible() -> None:
    from nonebot_plugin_chat.core.ego import proactive_chat_ctrl as ctrl
    from nonebot_plugin_chat.models import PrivateChatSession

    now = datetime.now(timezone.utc).timestamp()
    # (user_id, nickname, fav, last_proactive_message_time, unreplied_count, 最后私聊距今小时数, 是否应入选)
    cases = [
        ("u_fav_low", "低好感", 0.04, None, 0, 100.0, False),  # 好感度过低，不允许主动私聊
        ("u_fav_zero", "无好感", 0.0, None, 0, 100.0, False),  # 无好感度，不允许主动私聊
        ("u_cooling", "冷却中", 0.5, now - 12 * 3600, 0, 100.0, False),  # 24h 冷却期内（12h 前）→ 排除
        ("u_cool_ok", "冷却过", 0.5, now - 25 * 3600, 0, 100.0, True),  # 超过 24h 冷却 → 入选
        ("u_unreplied2", "未回复x2", 0.6, now - 48 * 3600, 2, 100.0, False),  # 连续 2 次未回复 → 排除
        ("u_unreplied1", "未回复x1", 0.6, now - 48 * 3600, 1, 100.0, True),  # 1 次未回复 → 入选
        ("u_never", "从未私聊", 0.8, None, 0, 100.0, True),  # 无主动私聊记录 → 入选
        ("u_active_now", "刚私聊过", 0.8, None, 0, 0.5, False),  # 半小时前私聊过 → 静默期内排除
        ("u_active_edge", "静默期内", 0.8, None, 0, 11.9, False),  # 11.9h 前私聊过 → 仍在静默期
        ("u_active_over", "静默期外", 0.8, None, 0, 12.1, True),  # 超过 12h → 可入选
    ]

    sessions = []
    for user_id, _, _, last_proactive, unreplied, active_hours, _ in cases:
        session = PrivateChatSession(
            user_id=user_id,
            session_key=f"qq_{user_id}",
            bot_id="bot1",
            last_message_time=now - active_hours * 3600,
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
        patch.object(ctrl.config, "proactive_chat_user_active_cooldown_hours", 12.0),
        patch("nonebot_plugin_larkuser.utils.user.get_user", side_effect=fake_get_user),
    ):
        controller = ctrl.ProactiveChatController(moonlark_main=None)  # type: ignore[arg-type]
        candidates, skipped = await controller._get_candidates()  # noqa: SLF001

    expected_ids = {c[0] for c in cases if c[6]}
    assert set(candidates) == expected_ids
    for user_id in expected_ids:
        assert candidates[user_id]["nickname"] == next(c[1] for c in cases if c[0] == user_id)
    # 各类筛除原因的统计
    assert skipped == {"favorability": 2, "cooldown": 1, "user_active": 2, "unreplied": 1}


async def test_check_and_send_skips_when_all_users_just_chatted() -> None:
    """所有用户都在私聊静默期内时，不进行 LLM 决策，也不发送任何主动私聊"""
    from nonebot_plugin_chat.core.ego import proactive_chat_ctrl as ctrl
    from nonebot_plugin_chat.models import PrivateChatSession

    now = datetime.now(timezone.utc).timestamp()
    sessions = [
        PrivateChatSession(
            user_id="u1",
            session_key="qq_u1",
            bot_id="bot1",
            last_message_time=now - 60,
            unreplied_count=0,
        ),
    ]

    fake_scalars = SimpleNamespace(all=lambda: sessions)
    fake_result = SimpleNamespace(scalars=lambda: fake_scalars)
    fake_db_session = SimpleNamespace(execute=AsyncMock(return_value=fake_result))
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = fake_db_session

    def fake_get_user(_user_id: str):
        return SimpleNamespace(
            get_nickname=lambda: "小明",
            get_display_fav=lambda: 0.8,
        )

    moonlark_main = SimpleNamespace(
        state={"sleep_mode": False},
        sleep_controller=SimpleNamespace(tiredness=0.0),
    )
    controller = ctrl.ProactiveChatController(moonlark_main=moonlark_main)  # type: ignore[arg-type]
    decide_mock = AsyncMock()

    with (
        patch.object(ctrl, "get_session", return_value=session_cm),
        patch.object(ctrl, "get_available_bot_ids", AsyncMock(return_value={"bot1"})),
        patch.object(ctrl.config, "proactive_chat_user_active_cooldown_hours", 12.0),
        patch("nonebot_plugin_larkuser.utils.user.get_user", side_effect=fake_get_user),
        patch.object(controller, "_llm_decide", decide_mock),
    ):
        await controller.check_and_send()

    decide_mock.assert_not_awaited()
    assert controller.decision_history[-1]["stage"] == "no_candidates"
    assert controller.decision_history[-1]["skipped"] == {
        "favorability": 0,
        "cooldown": 0,
        "user_active": 1,
        "unreplied": 0,
    }


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
        candidates, _skipped = await controller._get_candidates()  # noqa: SLF001
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
        "u_openid": SimpleNamespace(get_nickname=lambda: "小明", get_display_fav=lambda: 0.5),
        "u_qq": SimpleNamespace(get_nickname=lambda: "小明", get_display_fav=lambda: 0.5),
    }
    sent = AsyncMock()
    bot = SimpleNamespace(self_id="bot_online")

    with (
        patch.object(
            ctrl,
            "get_session",
            side_effect=[
                _fake_session_ctx([offline, online]),  # _get_candidates 读取全部记录
                _fake_session_cm(online),  # _send_proactive 读取目标记录
                _fake_session_cm(online),  # 更新未回复计数
            ],
        ),
        patch.object(ctrl, "get_available_bot_ids", AsyncMock(return_value={"bot_online"})),
        patch("nonebot_plugin_larkuser.utils.user.get_user", side_effect=lambda user_id: users[user_id]),
        patch("nonebot.get_bot", return_value=bot),
        patch("nonebot_plugin_chat.core.proactive_chat.send_proactive_private_message", new=sent),
    ):
        controller = ctrl.ProactiveChatController(moonlark_main=None)  # type: ignore[arg-type]
        candidates, _skipped = await controller._get_candidates()  # noqa: SLF001
        result = await controller._send_proactive(
            ctrl.ProactiveDecision(target_nickname="小明", topic="你好"), candidates
        )  # noqa: SLF001

    # bot 不可用的同名记录在候选筛选阶段就已被剔除
    assert set(candidates) == {"u_qq"}
    assert result == "已向 小明 发送主动私聊"
    sent.assert_awaited_once_with(bot, "u_qq", "你好")


async def test_send_proactive_reports_when_no_bot_available() -> None:
    """候选用户对应的 bot 不可用时，不发送并返回可读原因"""
    from nonebot_plugin_chat.core.ego import proactive_chat_ctrl as ctrl

    session = _make_session("u1", "bot_offline")
    controller = ctrl.ProactiveChatController(moonlark_main=None)  # type: ignore[arg-type]
    decision = ctrl.ProactiveDecision(target_nickname="小明", topic="你好")
    candidates = {"u1": {"nickname": "小明", "fav": 0.5, "last_message_time": 0.0}}
    sent = AsyncMock()

    with (
        patch.object(ctrl, "get_session", return_value=_fake_session_cm(session)),
        patch.object(ctrl, "get_available_bot_ids", AsyncMock(return_value=set())),
        patch("nonebot_plugin_chat.core.proactive_chat.send_proactive_private_message", new=sent),
    ):
        result = await controller._send_proactive(decision, candidates)  # noqa: SLF001

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


def _fake_session_cm(chat_session: Any) -> AsyncMock:
    """构造只返回一个私聊会话记录的假数据库会话"""
    fake_db_session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: chat_session)),
        commit=AsyncMock(),
    )
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = fake_db_session
    return session_cm


async def test_send_proactive_rejects_user_outside_candidates() -> None:
    """LLM 返回不在候选列表中的昵称时不应发送"""
    from nonebot_plugin_chat.core.ego import proactive_chat_ctrl as ctrl
    from nonebot_plugin_chat.core.ego.proactive_chat_ctrl import ProactiveDecision

    controller = ctrl.ProactiveChatController(moonlark_main=None)  # type: ignore[arg-type]
    decision = ProactiveDecision(skip=False, target_nickname="不存在的人", topic="在吗")
    candidates = {"u1": {"nickname": "小明", "fav": 0.5, "last_message_time": 0.0}}
    send_mock = AsyncMock()

    with (
        patch.object(ctrl, "get_session", return_value=_fake_session_cm(None)),
        patch("nonebot_plugin_chat.core.proactive_chat.send_proactive_private_message", send_mock),
    ):
        result = await controller._send_proactive(decision, candidates)  # noqa: SLF001

    assert "未找到用户" in result
    send_mock.assert_not_awaited()


async def test_send_proactive_skips_recently_active_user() -> None:
    """发送前再次校验：用户刚私聊过则跳过"""
    from nonebot_plugin_chat.core.ego import proactive_chat_ctrl as ctrl
    from nonebot_plugin_chat.core.ego.proactive_chat_ctrl import ProactiveDecision
    from nonebot_plugin_chat.models import PrivateChatSession

    now = datetime.now(timezone.utc).timestamp()
    chat_session = PrivateChatSession(user_id="u1", session_key="qq_u1", bot_id="bot1", last_message_time=now)
    controller = ctrl.ProactiveChatController(moonlark_main=None)  # type: ignore[arg-type]
    decision = ProactiveDecision(skip=False, target_nickname="小明", topic="在吗")
    candidates = {"u1": {"nickname": "小明", "fav": 0.8, "last_message_time": now}}
    send_mock = AsyncMock()

    with (
        patch.object(ctrl, "get_session", return_value=_fake_session_cm(chat_session)),
        patch.object(ctrl, "get_available_bot_ids", AsyncMock(return_value={"bot1"})),
        patch.object(ctrl.config, "proactive_chat_user_active_cooldown_hours", 12.0),
        patch("nonebot_plugin_chat.core.proactive_chat.send_proactive_private_message", send_mock),
    ):
        result = await controller._send_proactive(decision, candidates)  # noqa: SLF001

    assert "刚刚私聊过" in result
    send_mock.assert_not_awaited()


async def test_send_proactive_sends_and_increments_unreplied() -> None:
    from nonebot_plugin_chat.core.ego import proactive_chat_ctrl as ctrl
    from nonebot_plugin_chat.core.ego.proactive_chat_ctrl import ProactiveDecision
    from nonebot_plugin_chat.models import PrivateChatSession

    now = datetime.now(timezone.utc).timestamp()
    chat_session = PrivateChatSession(
        user_id="u1",
        session_key="qq_u1",
        bot_id="bot1",
        last_message_time=now - 48 * 3600,
        unreplied_count=0,
    )
    controller = ctrl.ProactiveChatController(moonlark_main=None)  # type: ignore[arg-type]
    decision = ProactiveDecision(skip=False, target_nickname="小明", topic="在吗")
    candidates = {"u1": {"nickname": "小明", "fav": 0.8, "last_message_time": now - 48 * 3600}}
    send_mock = AsyncMock()

    with (
        patch.object(ctrl, "get_session", return_value=_fake_session_cm(chat_session)),
        patch.object(ctrl, "get_available_bot_ids", AsyncMock(return_value={"bot1"})),
        patch.object(ctrl.config, "proactive_chat_user_active_cooldown_hours", 12.0),
        patch("nonebot_plugin_chat.core.proactive_chat.send_proactive_private_message", send_mock),
        patch("nonebot.get_bot", return_value="bot-instance"),
    ):
        result = await controller._send_proactive(decision, candidates)  # noqa: SLF001

    assert result == "已向 小明 发送主动私聊"
    send_mock.assert_awaited_once_with("bot-instance", "u1", "在吗")
    assert chat_session.unreplied_count == 1
