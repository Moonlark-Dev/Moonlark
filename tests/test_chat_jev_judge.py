"""chat 插件的 Jev 判定测试：回复后的 mood/好感度判定与触发概率预处理"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

if TYPE_CHECKING:
    from nonebot_plugin_chat.models import PreTriggerSignals
    from nonebot_plugin_chat.utils.jev_judge import ReplyEvaluation


def _noul(value: float) -> Any:
    from nonebot_plugin_jev.types import NoulAnswer

    return NoulAnswer(noul=value)


def _choice(value: str, confidence: float = 0.9) -> Any:
    from nonebot_plugin_jev.types import ChoiceAnswer

    return ChoiceAnswer(choice=value, confidence=confidence)


def _score(value: float, confidence: float = 0.8) -> Any:
    from nonebot_plugin_jev.types import ScoreAnswer

    return ScoreAnswer(score=value, confidence=confidence)


def _fake_processor(
    cached_messages: list[dict] | None = None,
    session_type: str = "group",
    nickname: str = "",
) -> Any:
    session = SimpleNamespace(
        session_id="pytest_jev_group",
        lang_str="mlsid::--lang=zh_hans",
        cached_messages=cached_messages or [],
        get_cached_messages_string=AsyncMock(return_value="[10:00:00] 小明: 你好"),
        get_session_type=Mock(return_value=session_type),
        nickname=nickname,
        set_interest=Mock(),
        add_event=AsyncMock(),
    )
    processor = SimpleNamespace(
        session=session,
        tool_manager=SimpleNamespace(set_mood=AsyncMock()),
        judge_user_behavior=AsyncMock(return_value=("已记录对小明的评价", True)),
        _latest_reasioning_content_cache="",
    )
    return processor


async def test_analyze_pre_trigger_maps_noul_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    """五个 Noul 答案按 0.5 阈值映射为 PreTriggerSignals"""
    from nonebot_plugin_chat.utils import jev_judge

    async def fake_ask(state: Any, questions: dict, **kwargs: Any) -> dict:
        values = {
            "truncate": 0.9,
            "help_needed": 0.2,
            "emotional_support_needed": 0.7,
            "chatting_alone": 0.1,
            "tech_topic": 0.6,
        }
        return {key: _noul(values[key]) for key in questions}

    with patch.object(jev_judge, "ask", AsyncMock(side_effect=fake_ask)):
        signals: "PreTriggerSignals" | None = await jev_judge.analyze_pre_trigger("聊天记录", "zh_hans")

    assert signals is not None
    assert signals.truncate is True
    assert signals.help_needed is False
    assert signals.emotional_support_needed is True
    assert signals.chatting_alone is False
    assert signals.tech_topic is True


async def test_analyze_pre_trigger_returns_none_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Jev 不可用时返回 None（调用方跳过门控）"""
    from nonebot_plugin_chat.utils import jev_judge

    with patch.object(jev_judge, "ask", AsyncMock(side_effect=RuntimeError("no key"))):
        assert await jev_judge.analyze_pre_trigger("聊天记录", "zh_hans") is None

    with patch.object(jev_judge, "ask", AsyncMock(return_value={})):
        assert await jev_judge.analyze_pre_trigger("聊天记录", "zh_hans") is None


async def test_evaluate_reply_builds_state_and_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    """evaluate_reply 把上下文/reasoning/输出/已发送消息放进 state 并解析答案"""
    from nonebot_plugin_chat.utils import jev_judge

    now = datetime.now()
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
            {"content": "你好", "nickname": "小明", "self": False, "message_id": "1", "send_time": now},
        ],
    )

    reasoning_message = SimpleNamespace(reasoning_content="用户打了招呼，应该回应")
    captured: dict[str, Any] = {}

    async def fake_ask(state: Any, questions: dict, **kwargs: Any) -> dict:
        captured["state"] = state
        captured["questions"] = questions
        return {
            "mood": _choice("joy"),
            "mood_intensity": _score(3.0),
            "interest": _score(2.0),
            "reply_required": _noul(0.9),
            "favor_target": _choice("小明"),
            "favor_score": _choice("1", confidence=0.8),
        }

    async def fake_text(key: str, lang_str: str, *args: Any, **kwargs: Any) -> str:
        return f"{key}:{args}"

    monkeypatch.setattr(jev_judge.jev_lang, "text", AsyncMock(side_effect=fake_text))

    with patch.object(jev_judge, "ask", AsyncMock(side_effect=fake_ask)):
        evaluation = await jev_judge.evaluate_reply(
            processor,  # type: ignore[arg-type]
            [reasoning_message],
            ["我觉得应该回一句"],
            now,
        )

    assert evaluation is not None
    # state 四要素齐全
    state = captured["state"]
    assert state["chat_context"] == "[10:00:00] 小明: 你好"
    assert state["reasoning_content"] == "用户打了招呼，应该回应"
    assert state["model_output"] == "我觉得应该回一句"
    assert state["sent_messages"] == ["Moonlark 的回复"]
    assert state["participants"] == ["小明"]
    # 答案解析
    assert evaluation.mood == "joy"
    assert evaluation.mood_intensity == pytest.approx(1.2)  # 等级 3 → 上限 1.2
    assert evaluation.interest == pytest.approx(2 / 3)
    assert evaluation.reply_required is True
    assert evaluation.favor_target == "小明"
    assert evaluation.favor_score == 1
    # reasoning_content 写回 processor，供 chat-monitor 读取
    assert processor._latest_reasioning_content_cache == "用户打了招呼，应该回应"


async def test_evaluate_reply_skips_no_mood_and_zero_score(monkeypatch: pytest.MonkeyPatch) -> None:
    """mood=none 与好感度 0 分都视为「无需变动」"""
    from nonebot_plugin_chat.utils import jev_judge

    processor = _fake_processor()

    async def fake_ask(state: Any, questions: dict, **kwargs: Any) -> dict:
        answers = {
            "mood": _choice("none"),
            "mood_intensity": _score(0.0),
            "interest": _score(0.0),
            "reply_required": _noul(0.1),
        }
        if "favor_target" in questions:
            answers["favor_target"] = _choice("none")
            answers["favor_score"] = _choice("0")
        return answers

    monkeypatch.setattr(jev_judge.jev_lang, "text", AsyncMock(side_effect=lambda *a, **k: str(a)))

    with patch.object(jev_judge, "ask", AsyncMock(side_effect=fake_ask)):
        evaluation = await jev_judge.evaluate_reply(processor, [], ["无变化"], datetime.now())  # type: ignore[arg-type]

    assert evaluation is not None
    assert evaluation.mood is None
    assert evaluation.favor_target is None
    assert evaluation.favor_changed is False
    assert evaluation.reply_required is False


async def test_evaluate_reply_private_skips_favor_target_question(monkeypatch: pytest.MonkeyPatch) -> None:
    """私聊不提问 favor_target，被评价对象自动填为会话中的对话者"""
    from nonebot_plugin_chat.utils import jev_judge

    now = datetime.now()
    processor = _fake_processor(
        cached_messages=[
            {"content": "你好", "nickname": "小明", "self": False, "message_id": "1", "send_time": now},
        ],
        session_type="private",
        nickname="小明",
    )
    captured: dict[str, Any] = {}

    async def fake_ask(state: Any, questions: dict, **kwargs: Any) -> dict:
        captured["questions"] = questions
        # 私聊中 Jev 只会回答 favor_score
        return {
            "mood": _choice("joy"),
            "mood_intensity": _score(2.0),
            "interest": _score(1.0),
            "reply_required": _noul(0.1),
            "favor_score": _choice("1", confidence=0.7),
        }

    monkeypatch.setattr(jev_judge.jev_lang, "text", AsyncMock(side_effect=lambda key, *a, **k: key))

    with patch.object(jev_judge, "ask", AsyncMock(side_effect=fake_ask)):
        evaluation = await jev_judge.evaluate_reply(processor, [], ["私聊回复"], now)  # type: ignore[arg-type]

    assert evaluation is not None
    # 私聊不提交 favor_target 问题，但仍然提交 favor_score
    assert "favor_target" not in captured["questions"]
    assert "favor_score" in captured["questions"]
    # 目标由会话自动填充，分数来自 Jev
    assert evaluation.favor_target == "小明"
    assert evaluation.favor_score == 1
    assert evaluation.favor_changed is True


async def test_evaluate_reply_private_falls_back_to_cached_nickname(monkeypatch: pytest.MonkeyPatch) -> None:
    """私聊 session.nickname 为空时，退回消息缓存中唯一的非自身昵称"""
    from nonebot_plugin_chat.utils import jev_judge

    now = datetime.now()
    processor = _fake_processor(
        cached_messages=[
            {"content": "你好", "nickname": "小红", "self": False, "message_id": "1", "send_time": now},
        ],
        session_type="private",
        nickname="",
    )

    async def fake_ask(state: Any, questions: dict, **kwargs: Any) -> dict:
        return {"favor_score": _choice("-1", confidence=0.6)}

    monkeypatch.setattr(jev_judge.jev_lang, "text", AsyncMock(side_effect=lambda key, *a, **k: key))

    with patch.object(jev_judge, "ask", AsyncMock(side_effect=fake_ask)):
        evaluation = await jev_judge.evaluate_reply(processor, [], ["回复"], now)  # type: ignore[arg-type]

    assert evaluation is not None
    assert evaluation.favor_target == "小红"
    assert evaluation.favor_score == -1


async def test_evaluate_reply_group_still_asks_favor_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """群聊行为不变：仍然提问 favor_target，并且只接受 participants 中的名字"""
    from nonebot_plugin_chat.utils import jev_judge

    now = datetime.now()
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

    async def fake_ask(state: Any, questions: dict, **kwargs: Any) -> dict:
        captured["questions"] = questions
        return {"favor_target": _choice("小明"), "favor_score": _choice("2", confidence=0.9)}

    monkeypatch.setattr(jev_judge.jev_lang, "text", AsyncMock(side_effect=lambda key, *a, **k: key))

    with patch.object(jev_judge, "ask", AsyncMock(side_effect=fake_ask)):
        evaluation = await jev_judge.evaluate_reply(processor, [], ["群聊回复"], now)  # type: ignore[arg-type]

    assert evaluation is not None
    assert "favor_target" in captured["questions"]
    assert evaluation.favor_target == "小明"
    assert evaluation.favor_score == 2


async def test_apply_evaluation_pushes_event_on_favor_change() -> None:
    """好感度变动成功时向会话推送事件，失败时不推送"""
    from nonebot_plugin_chat.utils.jev_judge import ReplyEvaluation, apply_reply_evaluation

    processor = _fake_processor()
    evaluation = ReplyEvaluation(mood="joy", mood_intensity=1.0, mood_reason="原因", interest=0.5)

    await apply_reply_evaluation(processor, evaluation)  # type: ignore[arg-type]

    processor.tool_manager.set_mood.assert_awaited_once_with("joy", "原因", 1.0)
    processor.session.set_interest.assert_called_once_with(0.5)
    # 没有好感度评价时不推送事件
    processor.session.add_event.assert_not_awaited()

    evaluation2 = ReplyEvaluation(favor_target="小明", favor_score=1, favor_reason="表现友善")
    await apply_reply_evaluation(processor, evaluation2)  # type: ignore[arg-type]

    processor.judge_user_behavior.assert_awaited_once_with("小明", 1, "表现友善")
    processor.session.add_event.assert_awaited_once_with("已记录对小明的评价", "none")

    # 好感度变动失败（冷却/上限等）时不推送事件
    processor.judge_user_behavior = AsyncMock(return_value=("冷却中", False))
    processor.session.add_event.reset_mock()
    await apply_reply_evaluation(processor, evaluation2)  # type: ignore[arg-type]
    processor.session.add_event.assert_not_awaited()


async def test_apply_evaluation_none_mood_is_noop() -> None:
    from nonebot_plugin_chat.utils.jev_judge import ReplyEvaluation, apply_reply_evaluation

    processor = _fake_processor()
    await apply_reply_evaluation(processor, ReplyEvaluation(mood=None, interest=None))  # type: ignore[arg-type]

    processor.tool_manager.set_mood.assert_not_awaited()
    processor.session.set_interest.assert_not_called()


def test_has_sent_message_since_filters_by_time_and_message_id() -> None:
    """只有本轮回复期间真正发出的消息才算「已发送」"""
    from nonebot_plugin_chat.core.message import MessageQueue

    now = datetime.now()
    session = SimpleNamespace(
        cached_messages=[
            {"self": True, "message_id": "", "send_time": now},  # 事件（无消息 ID）不算
            {"self": True, "message_id": "9", "send_time": now - timedelta(minutes=5)},  # 上一轮的回复
            {"self": False, "message_id": "1", "send_time": now},  # 用户消息不算
        ],
    )
    processor = SimpleNamespace(session=session)
    queue = MessageQueue(processor)  # type: ignore[arg-type]

    assert queue._has_sent_message_since(now) is False

    session.cached_messages.append({"self": True, "message_id": "10", "send_time": now})
    assert queue._has_sent_message_since(now) is True
