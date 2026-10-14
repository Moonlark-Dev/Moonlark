"""chat 插件好感度评价的门控测试

覆盖三块：

- ``utils/simhash.py``：<=5 字完全匹配、>5 字 simhash 模糊匹配；
- ``utils/fav_judge.py``：冷却 / 每日上限 / 重复消息抬升置信度的纯逻辑；
- 落库往返：每次变动写一条记录，冷却、当日累计与重复次数都由这张表推导。
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# simhash 指纹
# ---------------------------------------------------------------------------


def test_short_message_requires_exact_match() -> None:
    """<=5 字的消息只有完全相同才算「出现过」"""
    from nonebot_plugin_chat.utils.simhash import build_message_fingerprint, is_same_message

    target = build_message_fingerprint("谢谢猫猫")
    assert target == "e:谢谢猫猫"
    # 五个字仍然走完全匹配
    assert build_message_fingerprint("谢谢猫猫喵") == "e:谢谢猫猫喵"
    assert is_same_message(target, build_message_fingerprint("谢谢猫猫")) is True
    # 只差一个字也不算同一条
    assert is_same_message(target, build_message_fingerprint("谢谢猫喵")) is False
    assert is_same_message(target, build_message_fingerprint("谢谢猫猫喵")) is False


def test_normalization_ignores_whitespace_and_case() -> None:
    """空白与大小写不影响指纹"""
    from nonebot_plugin_chat.utils.simhash import build_message_fingerprint

    assert build_message_fingerprint(" 你好 世界 ") == build_message_fingerprint("你好世界")
    assert build_message_fingerprint("Hello World") == build_message_fingerprint("hello world")
    # 纯空白没有指纹
    assert build_message_fingerprint("   ") == ""


def test_long_message_matches_small_edits_only() -> None:
    """>5 字走 simhash：差一个字算同一条，无关的两句话不算"""
    from nonebot_plugin_chat.utils.simhash import build_message_fingerprint, is_same_message

    original = "今天天气真好啊我们出去玩玩吧"
    edited = "今天天气真好啊我们出去走走吧"
    unrelated = "帮我写一段快速排序的 Python 代码"

    assert is_same_message(build_message_fingerprint(original), build_message_fingerprint(original)) is True
    assert is_same_message(build_message_fingerprint(original), build_message_fingerprint(edited)) is True
    assert is_same_message(build_message_fingerprint(original), build_message_fingerprint(unrelated)) is False


def test_long_message_fingerprint_encodes_length() -> None:
    """长度差太多的长消息不算同一条（防止短句之间误判）"""
    from nonebot_plugin_chat.utils.simhash import build_message_fingerprint, is_same_message

    short_text = "今天天气真好啊"
    long_text = "今天天气真好啊我们出去玩玩吧顺便再去公园散散步"
    short = build_message_fingerprint(short_text)
    long = build_message_fingerprint(long_text)
    assert short.startswith(f"s:{len(short_text)}:")
    assert long.startswith(f"s:{len(long_text)}:")
    assert is_same_message(short, long) is False


def test_count_matching_fingerprints() -> None:
    """批量统计时只有与目标同一条消息的指纹才计数"""
    from nonebot_plugin_chat.utils.simhash import build_message_fingerprint, count_matching_fingerprints

    target = build_message_fingerprint("今天天气真好啊我们出去玩玩吧")
    fingerprints = [
        build_message_fingerprint("今天天气真好啊我们出去走走吧"),  # 差一个字
        build_message_fingerprint("今天天气真好啊我们出去玩玩吧"),  # 完全相同
        build_message_fingerprint("帮我写一段快速排序的 Python 代码"),
        "",
    ]
    assert count_matching_fingerprints(fingerprints, target) == 2
    assert count_matching_fingerprints(fingerprints, "") == 0


# ---------------------------------------------------------------------------
# 门控逻辑（纯函数）
# ---------------------------------------------------------------------------


def test_required_confidence_scales_with_repeat_count_and_caps() -> None:
    """重复次数越多要求越高，且封顶在最大值"""
    from nonebot_plugin_chat.utils.fav_judge import (
        FAV_JUDGE_CONFIDENCE_MAX,
        FAV_JUDGE_CONFIDENCE_STEP,
        get_required_confidence,
    )

    # 第一次出现（0 次历史）完全不受影响
    assert get_required_confidence(0) == 0.0
    assert get_required_confidence(-1) == 0.0
    assert get_required_confidence(1) == pytest.approx(FAV_JUDGE_CONFIDENCE_STEP)
    assert get_required_confidence(3) == pytest.approx(3 * FAV_JUDGE_CONFIDENCE_STEP)
    assert get_required_confidence(9) == pytest.approx(FAV_JUDGE_CONFIDENCE_MAX)
    assert get_required_confidence(100) == pytest.approx(FAV_JUDGE_CONFIDENCE_MAX)


def test_decide_favor_change_allows_first_time_message() -> None:
    """没有任何历史时，置信度为 0 也能正常提升好感度"""
    from nonebot_plugin_chat.utils.fav_judge import FAV_JUDGE_STEP, FavorJudgeState, decide_favor_change

    now = datetime.now()
    decision = decide_favor_change(2, 0.0, FavorJudgeState(), now)
    assert decision.rejection is None
    assert decision.delta == pytest.approx(2 * FAV_JUDGE_STEP)
    assert decision.required_confidence == 0.0


def test_decide_favor_change_enforces_cooldown() -> None:
    """提升好感度冷却 1 小时，降低好感度只冷却 0.5 小时"""
    from nonebot_plugin_chat.utils.fav_judge import FavorJudgeState, decide_favor_change

    now = datetime.now()
    state = FavorJudgeState(last_judge_time=now - timedelta(minutes=30))
    assert decide_favor_change(1, 1.0, state, now).rejection == "cooldown"
    assert decide_favor_change(-1, 1.0, state, now).rejection is None

    state = FavorJudgeState(last_judge_time=now - timedelta(hours=2))
    assert decide_favor_change(1, 1.0, state, now).rejection is None


def test_decide_favor_change_enforces_daily_limit() -> None:
    """当日累计变动超过上限时拒绝"""
    from nonebot_plugin_chat.utils.fav_judge import FAV_JUDGE_DAILY_LIMIT, FavorJudgeState, decide_favor_change

    now = datetime.now()
    state = FavorJudgeState(
        last_judge_time=now - timedelta(hours=5),
        daily_score=FAV_JUDGE_DAILY_LIMIT - 0.0004,
    )
    assert decide_favor_change(2, 1.0, state, now).rejection == "daily_limit"
    assert decide_favor_change(1, 1.0, state, now).rejection is None


def test_duplicate_message_raises_confidence_requirement() -> None:
    """同一条消息出现过 5 次后，需要 0.5 以上的置信度"""
    from nonebot_plugin_chat.utils.fav_judge import FavorJudgeState, decide_favor_change

    now = datetime.now()
    state = FavorJudgeState(last_judge_time=now - timedelta(hours=5), similar_count=5)

    rejected = decide_favor_change(1, 0.4, state, now)
    assert rejected.rejection == "low_confidence"
    assert rejected.delta == 0.0
    assert rejected.required_confidence == pytest.approx(0.5)
    assert rejected.similar_count == 5

    assert decide_favor_change(1, 0.6, state, now).rejection is None


def test_duplicate_gate_only_applies_to_favor_increase() -> None:
    """降低好感度不看重复消息，也不受置信度影响"""
    from nonebot_plugin_chat.utils.fav_judge import FavorJudgeState, decide_favor_change

    now = datetime.now()
    state = FavorJudgeState(last_judge_time=now - timedelta(hours=5), similar_count=50)
    decision = decide_favor_change(-1, 0.0, state, now)
    assert decision.rejection is None
    assert decision.delta < 0


def test_confidence_cap_never_hard_blocks() -> None:
    """置信度要求封顶在 0.9：足够确信的判定仍然可以通过"""
    from nonebot_plugin_chat.utils.fav_judge import FAV_JUDGE_CONFIDENCE_MAX, FavorJudgeState, decide_favor_change

    now = datetime.now()
    state = FavorJudgeState(last_judge_time=now - timedelta(hours=5), similar_count=1000)
    assert decide_favor_change(1, 0.89, state, now).rejection == "low_confidence"
    assert decide_favor_change(1, FAV_JUDGE_CONFIDENCE_MAX, state, now).rejection is None


# ---------------------------------------------------------------------------
# processor 接线
# ---------------------------------------------------------------------------


def _fake_judge_processor() -> Any:
    from unittest.mock import AsyncMock

    session = SimpleNamespace(
        session_id="qq_1",
        get_users=AsyncMock(return_value={"小明": "u1"}),
        text=AsyncMock(side_effect=lambda key, *args: f"{key}|{args}"),
    )
    return SimpleNamespace(session=session, send_judge_response=AsyncMock())


def _fake_user() -> Any:
    from unittest.mock import AsyncMock

    return SimpleNamespace(get_register_time=lambda: datetime(2026, 1, 1), add_fav=AsyncMock())


async def test_judge_user_behavior_blocks_low_confidence_repeat(monkeypatch: pytest.MonkeyPatch) -> None:
    """重复消息且置信度不达标时，不写记录也不加好感度"""
    from unittest.mock import AsyncMock

    from nonebot_plugin_chat.core import processor as processor_module
    from nonebot_plugin_chat.utils.fav_judge import FavorJudgeState

    processor = _fake_judge_processor()
    user = _fake_user()
    monkeypatch.setattr(processor_module, "get_user", AsyncMock(return_value=user))
    record = AsyncMock()
    monkeypatch.setattr(processor_module, "record_favor_change", record)
    monkeypatch.setattr(
        processor_module,
        "get_favor_judge_state",
        AsyncMock(return_value=FavorJudgeState(similar_count=5)),
    )

    text, changed = await processor_module.MessageProcessor.judge_user_behavior(
        processor, "小明", 1, "表现友善", "今天天气真好啊我们出去玩玩吧", 0.3
    )

    assert changed is False
    assert "judge.low_confidence" in text
    user.add_fav.assert_not_awaited()
    record.assert_not_awaited()


async def test_judge_user_behavior_records_successful_change(monkeypatch: pytest.MonkeyPatch) -> None:
    """门控通过后写一条记录并加好感度（不再读写 LarkUser config）"""
    from unittest.mock import AsyncMock

    from nonebot_plugin_chat.core import processor as processor_module
    from nonebot_plugin_chat.utils.fav_judge import FAV_JUDGE_STEP, FavorJudgeState

    processor = _fake_judge_processor()
    user = _fake_user()
    monkeypatch.setattr(processor_module, "get_user", AsyncMock(return_value=user))
    record = AsyncMock()
    monkeypatch.setattr(processor_module, "record_favor_change", record)
    monkeypatch.setattr(
        processor_module,
        "get_favor_judge_state",
        AsyncMock(return_value=FavorJudgeState()),
    )
    # 旧实现写的是 LarkUser config，这里确认它已经不参与判定
    user.get_config_key = lambda *args, **kwargs: pytest.fail("不应再读 chat_fav_judge_cache")
    user.set_config_key = AsyncMock(side_effect=AssertionError("不应再写 chat_fav_judge_cache"))

    text, changed = await processor_module.MessageProcessor.judge_user_behavior(
        processor, "小明", 2, "表现友善", "今天天气真好啊我们出去玩玩吧", 0.9
    )

    assert changed is True
    assert "judge.success" in text
    user.add_fav.assert_awaited_once_with(2 * FAV_JUDGE_STEP)
    assert record.await_count == 1
    assert record.await_args.kwargs["user_id"] == "u1"
    assert record.await_args.kwargs["session_id"] == "qq_1"
    assert record.await_args.kwargs["confidence"] == pytest.approx(0.9)
    assert record.await_args.kwargs["message"] == "今天天气真好啊我们出去玩玩吧"


# ---------------------------------------------------------------------------
# 落库往返
# ---------------------------------------------------------------------------


async def test_favor_judge_record_roundtrip() -> None:
    """真实数据库下：写一条变动 → 冷却 / 当日累计 / 重复次数都能读回来"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from nonebot_plugin_chat.models import FavorJudgeRecord
    from nonebot_plugin_chat.utils import fav_judge

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(FavorJudgeRecord.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    base = datetime.combine(datetime.now().date(), time(12, 0))
    with patch.object(fav_judge, "get_session", lambda: factory()):
        await fav_judge.record_favor_change(
            user_id="u1",
            session_id="qq_1",
            nickname="小明",
            message="今天天气真好啊我们出去玩玩吧",
            score=2,
            delta=0.0008,
            confidence=0.9,
            reason="表现友善",
            now=base,
        )
        # 隔了两个小时（冷却已过），同样的话改一个字再出现一次
        similar = await fav_judge.get_favor_judge_state(
            "u1",
            fav_judge.build_message_fingerprint("今天天气真好啊我们出去走走吧"),
            base + timedelta(hours=2),
        )
        # 完全无关的消息不该被算成重复
        unrelated = await fav_judge.get_favor_judge_state(
            "u1",
            fav_judge.build_message_fingerprint("帮我写一段快速排序的 Python 代码"),
            base + timedelta(hours=2),
        )
        # 冷却窗口内再评价一次：能读到上一次的时间
        cooling = await fav_judge.get_favor_judge_state(
            "u1",
            fav_judge.build_message_fingerprint("今天天气真好啊我们出去玩玩吧"),
            base + timedelta(minutes=10),
        )
        # 另一个用户的记录互不影响
        other_user = await fav_judge.get_favor_judge_state(
            "u2", fav_judge.build_message_fingerprint("今天天气真好啊我们出去玩玩吧"), base + timedelta(hours=2)
        )

    await engine.dispose()

    assert similar.similar_count == 1
    assert similar.daily_score == pytest.approx(0.0008)
    assert unrelated.similar_count == 0
    assert cooling.last_judge_time == base
    assert other_user.similar_count == 0
    assert other_user.last_judge_time is None
