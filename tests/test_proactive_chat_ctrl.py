"""主动私聊控制器测试：分级冷却与连续未回复限制"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.parametrize(
    ("favorability", "expected"),
    [
        (0.5, 12.0),
        (0.301, 12.0),
        (0.3, 24.0),
        (0.151, 24.0),
        (0.15, 36.0),
        (0.051, 36.0),
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
        ("u_cooling", "冷却中", 0.5, now - 6 * 3600, 0, False),  # 12h 冷却期内（6h 前）→ 排除
        ("u_cool_ok", "冷却过", 0.5, now - 13 * 3600, 0, True),  # 超过 12h 冷却 → 入选
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
        patch("nonebot_plugin_larkuser.utils.user.get_user", side_effect=fake_get_user),
    ):
        controller = ctrl.ProactiveChatController(moonlark_main=None)  # type: ignore[arg-type]
        candidates = await controller._get_candidates()  # noqa: SLF001

    expected_ids = {c[0] for c in cases if c[5]}
    assert set(candidates) == expected_ids
    for user_id in expected_ids:
        assert candidates[user_id]["nickname"] == next(c[1] for c in cases if c[0] == user_id)
