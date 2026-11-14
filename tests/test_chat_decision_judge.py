"""chat 插件的 Decisions API 判定测试：回复后的 mood/好感度判定与触发概率预处理"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

if TYPE_CHECKING:
    from nonebot_plugin_chat.models import PreTriggerSignals


def _noul(value: float) -> Any:
    from nonebot_plugin_decision.types import NoulAnswer

    return NoulAnswer(noul=value)


def _choice(value: str, confidence: float = 0.9) -> Any:
    from nonebot_plugin_decision.types import ChoiceAnswer

    return ChoiceAnswer(choice=value, confidence=confidence)


def _score(value: float, confidence: float = 0.8) -> Any:
    from nonebot_plugin_decision.types import ScoreAnswer

    return ScoreAnswer(score=value, confidence=confidence)


def _fake_processor(
    cached_messages: list[dict[str, Any]] | None = None,
    session_type: str = "group",
    nickname: str = "",
) -> Any:
    session = SimpleNamespace(
        session_id="pytest_decision_group",
        lang_str="mlsid::--lang=zh_hans",
        cached_messages=cached_messages or [],
        get_cached_messages_string=AsyncMock(return_value="[10:00:00] 小明: 你好"),
        get_session_type=Mock(return_value=session_type),
        nickname=nickname,
        set_interest=Mock(),
        add_event=AsyncMock(),
    )
    return SimpleNamespace(
        session=session,
        tool_manager=SimpleNamespace(set_mood=AsyncMock()),
        judge_user_behavior=AsyncMock(return_value=("已记录对小明的评价", True)),
        _latest_reasioning_content_cache="",
    )


async def test_analyze_pre_trigger_maps_noul_answers() -> None:
    """五个 Noul 答案按 0.5 阈值映射为 PreTriggerSignals"""
    from nonebot_plugin_chat.utils import decision_judge

    async def fake_ask(_state: Any, questions: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        values = {
            "truncate": 0.9,
            "help_needed": 0.2,
            "emotional_support_needed": 0.7,
            "chatting_alone": 0.1,
            "tech_topic": 0.6,
        }
        return {key: _noul(values[key]) for key in questions}

    with patch.object(decision_judge, "ask", AsyncMock(side_effect=fake_ask)):
        signals: PreTriggerSignals | None = await decision_judge.analyze_pre_trigger("聊天记录", "zh_hans")

    assert signals is not None
    assert signals.truncate is True
    assert signals.help_needed is False
    assert signals.emotional_support_needed is True
    assert signals.chatting_alone is False
    assert signals.tech_topic is True


async def test_analyze_pre_trigger_returns_none_on_empty_or_failure() -> None:
    """空聊天记录或 Decisions API 不可用时返回 None（调用方跳过门控）"""
    from nonebot_plugin_chat.utils import decision_judge

    ask_spy = AsyncMock()
    with patch.object(decision_judge, "ask", ask_spy):
        assert await decision_judge.analyze_pre_trigger("   ", "zh_hans") is None
    ask_spy.assert_not_awaited()

    with patch.object(decision_judge, "ask", AsyncMock(side_effect=RuntimeError("no key"))):
        assert await decision_judge.analyze_pre_trigger("聊天记录", "zh_hans") is None

    with patch.object(decision_judge, "ask", AsyncMock(return_value={})):
        assert await decision_judge.analyze_pre_trigger("聊天记录", "zh_hans") is None


async def test_evaluate_reply_builds_state_and_ascii_option_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """evaluate_reply 使用合法 ASCII 键提交群聊参与者与好感档位，并还原为原昵称和分值"""
    from nonebot_plugin_chat.utils import decision_judge

    now = datetime.now(timezone.utc)
    sent_at = now + timedelta(seconds=1)
    processor = _fake_processor(
        cached_messages=[
            {
                "content": "Moonlark 的回复",
                "nickname": "Moonlark",
                "self": True,
                "message_id": "12345",
                "send_time": sent_at,
            },
            {"content": "你好", "nickname": "小明 🌟", "self": False, "message_id": "1", "send_time": now},
            {"content": "我也来了", "nickname": "none", "self": False, "message_id": "2", "send_time": now},
        ],
    )

    reasoning_message = SimpleNamespace(reasoning_content="用户打了招呼，应该回应")
    captured: dict[str, Any] = {}

    async def fake_ask(state: Any, questions: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        captured["state"] = state
        captured["questions"] = questions
        return {
            "mood": _choice("joy"),
            "mood_intensity": _score(3.0),
            "interest": _score(2.0),
            "reply_required": _noul(0.9),
            "favor_target": _choice("p_0"),
            "favor_score": _choice("plus_1", confidence=0.8),
        }

    async def fake_text(key: str, _lang_str: str, *args: Any) -> str:
        return f"{key}:{args}"

    monkeypatch.setattr(decision_judge.decision_lang, "text", AsyncMock(side_effect=fake_text))

    with patch.object(decision_judge, "ask", AsyncMock(side_effect=fake_ask)):
        evaluation = await decision_judge.evaluate_reply(
            processor,
            [reasoning_message],
            ["我觉得应该回一句"],
            now,
        )

    assert evaluation is not None
    state = captured["state"]
    assert state["chat_context"] == "[10:00:00] 小明: 你好"
    assert state["reasoning_content"] == "用户打了招呼，应该回应"
    assert state["model_output"] == "我觉得应该回一句"
    assert state["sent_messages"] == ["Moonlark 的回复"]
    assert state["participants"] == ["小明 🌟", "none"]

    # 即使昵称含中文/空格/Emoji 甚至字面量 "none"，选项键依然全部为合法的 ASCII 键且不冲突
    target_criteria = captured["questions"]["favor_target"].criteria
    assert set(target_criteria) == {"p_0", "p_1", "none"}
    assert target_criteria["p_0"] == "小明 🌟"
    assert target_criteria["p_1"] == "none"

    score_criteria = captured["questions"]["favor_score"].criteria
    assert set(score_criteria) == {"plus_2", "plus_1", "zero", "minus_1", "minus_2"}

    # 答案解析还原
    assert evaluation.mood == "joy"
    assert evaluation.mood_intensity == pytest.approx(1.2)
    assert evaluation.interest == pytest.approx(2 / 3)
    assert evaluation.reply_required is True
    assert evaluation.favor_target == "小明 🌟"
    assert evaluation.favor_score == 1
    assert processor._latest_reasioning_content_cache == "用户打了招呼，应该回应"  # ruff: ignore[private-member-access]


async def test_evaluate_reply_skips_no_mood_and_zero_score(monkeypatch: pytest.MonkeyPatch) -> None:
    """mood=none 与好感度 zero 都视为「无需变动」"""
    from nonebot_plugin_chat.utils import decision_judge

    processor = _fake_processor()

    async def fake_ask(_state: Any, questions: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        answers: dict[str, Any] = {
            "mood": _choice("none"),
            "mood_intensity": _score(0.0),
            "interest": _score(0.0),
            "reply_required": _noul(0.1),
        }
        if "favor_target" in questions:
            answers["favor_target"] = _choice("none")
            answers["favor_score"] = _choice("zero")
        return answers

    monkeypatch.setattr(decision_judge.decision_lang, "text", AsyncMock(side_effect=lambda *a, **_k: str(a)))

    with patch.object(decision_judge, "ask", AsyncMock(side_effect=fake_ask)):
        evaluation = await decision_judge.evaluate_reply(processor, [], ["无变化"], datetime.now(timezone.utc))

    assert evaluation is not None
    assert evaluation.mood is None
    assert evaluation.favor_target is None
    assert evaluation.favor_changed is False
    assert evaluation.reply_required is False


async def test_evaluate_reply_private_skips_favor_target_question(monkeypatch: pytest.MonkeyPatch) -> None:
    """私聊不提问 favor_target，被评价对象自动填为会话中的对话者"""
    from nonebot_plugin_chat.utils import decision_judge

    now = datetime.now(timezone.utc)
    processor = _fake_processor(
        cached_messages=[
            {"content": "你好", "nickname": "小明", "self": False, "message_id": "1", "send_time": now},
        ],
        session_type="private",
        nickname="小明",
    )
    captured: dict[str, Any] = {}

    async def fake_ask(_state: Any, questions: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        captured["questions"] = questions
        return {
            "mood": _choice("joy"),
            "mood_intensity": _score(2.0),
            "interest": _score(1.0),
            "reply_required": _noul(0.1),
            "favor_score": _choice("plus_1", confidence=0.7),
        }

    monkeypatch.setattr(decision_judge.decision_lang, "text", AsyncMock(side_effect=lambda key, *_a, **_k: key))

    with patch.object(decision_judge, "ask", AsyncMock(side_effect=fake_ask)):
        evaluation = await decision_judge.evaluate_reply(processor, [], ["私聊回复"], now)

    assert evaluation is not None
    assert "favor_target" not in captured["questions"]
    assert "favor_score" in captured["questions"]
    assert evaluation.favor_target == "小明"
    assert evaluation.favor_score == 1
    assert evaluation.favor_changed is True


async def test_evaluate_reply_private_falls_back_to_cached_nickname(monkeypatch: pytest.MonkeyPatch) -> None:
    """私聊 session.nickname 为空时，退回消息缓存中唯一的非自身昵称"""
    from nonebot_plugin_chat.utils import decision_judge

    now = datetime.now(timezone.utc)
    processor = _fake_processor(
        cached_messages=[
            {"content": "你好", "nickname": "小红", "self": False, "message_id": "1", "send_time": now},
        ],
        session_type="private",
        nickname="",
    )

    async def fake_ask(_state: Any, _questions: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        return {"favor_score": _choice("minus_1", confidence=0.6)}

    monkeypatch.setattr(decision_judge.decision_lang, "text", AsyncMock(side_effect=lambda key, *_a, **_k: key))

    with patch.object(decision_judge, "ask", AsyncMock(side_effect=fake_ask)):
        evaluation = await decision_judge.evaluate_reply(processor, [], ["回复"], now)

    assert evaluation is not None
    assert evaluation.favor_target == "小红"
    assert evaluation.favor_score == -1


async def test_evaluate_reply_group_still_asks_favor_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """群聊仍然提问 favor_target，并把 p_0 映射回参与者原名"""
    from nonebot_plugin_chat.utils import decision_judge

    now = datetime.now(timezone.utc)
    processor = _fake_processor(
        cached_messages=[
            {
                "content": "Moonlark 的回复",
                "nickname": "Moonlark",
                "self": True,
                "message_id": "12345",
                "send_time": now + timedelta(seconds=1),
            },
            {"content": "你好", "nickname": "小明", "self": False, "message_id": "1", "send_time": now},
        ],
        session_type="group",
        nickname="小明",
    )
    captured: dict[str, Any] = {}

    async def fake_ask(_state: Any, questions: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        captured["questions"] = questions
        return {"favor_target": _choice("p_0"), "favor_score": _choice("plus_2", confidence=0.9)}

    monkeypatch.setattr(decision_judge.decision_lang, "text", AsyncMock(side_effect=lambda key, *_a, **_k: key))

    with patch.object(decision_judge, "ask", AsyncMock(side_effect=fake_ask)):
        evaluation = await decision_judge.evaluate_reply(processor, [], ["群聊回复"], now)

    assert evaluation is not None
    assert "favor_target" in captured["questions"]
    assert evaluation.favor_target == "小明"
    assert evaluation.favor_score == 2
    assert evaluation.favor_message == "你好"
    assert evaluation.favor_confidence == pytest.approx(0.9)


async def test_apply_evaluation_pushes_event_on_favor_change() -> None:
    """好感度变动成功时向会话推送事件，失败时不推送"""
    from nonebot_plugin_chat.utils.decision_judge import ReplyEvaluation, apply_reply_evaluation

    processor = _fake_processor()
    evaluation = ReplyEvaluation(mood="joy", mood_intensity=1.0, mood_reason="原因", interest=0.5)

    await apply_reply_evaluation(processor, evaluation)

    processor.tool_manager.set_mood.assert_awaited_once_with("joy", "原因", 1.0)
    processor.session.set_interest.assert_called_once_with(0.5)
    processor.session.add_event.assert_not_awaited()

    evaluation2 = ReplyEvaluation(favor_target="小明", favor_score=1, favor_reason="表现友善")
    await apply_reply_evaluation(processor, evaluation2)

    processor.judge_user_behavior.assert_awaited_once_with("小明", 1, "表现友善", "", 0.0)
    processor.session.add_event.assert_awaited_once_with("已记录对小明的评价", "none")

    processor.judge_user_behavior = AsyncMock(return_value=("冷却中", False))
    processor.session.add_event.reset_mock()
    await apply_reply_evaluation(processor, evaluation2)
    processor.session.add_event.assert_not_awaited()


async def test_apply_evaluation_none_mood_is_noop() -> None:
    from nonebot_plugin_chat.utils.decision_judge import ReplyEvaluation, apply_reply_evaluation

    processor = _fake_processor()
    await apply_reply_evaluation(processor, ReplyEvaluation(mood=None, interest=None))

    processor.tool_manager.set_mood.assert_not_awaited()
    processor.session.set_interest.assert_not_called()


def test_has_sent_message_since_filters_by_time_and_message_id() -> None:
    """只有本轮回复期间真正发出的消息才算「已发送」"""
    from nonebot_plugin_chat.core.message import MessageQueue

    now = datetime.now(timezone.utc)
    session = SimpleNamespace(
        cached_messages=[
            {"self": True, "message_id": "", "send_time": now},
            {"self": True, "message_id": "9", "send_time": now - timedelta(minutes=5)},
            {"self": False, "message_id": "1", "send_time": now},
        ],
    )
    processor = SimpleNamespace(session=session)
    queue = MessageQueue(processor)  # type: ignore[arg-type]

    assert queue._has_sent_message_since(now) is False  # ruff: ignore[private-member-access]

    session.cached_messages.append({"self": True, "message_id": "10", "send_time": now})
    assert queue._has_sent_message_since(now) is True  # ruff: ignore[private-member-access]
