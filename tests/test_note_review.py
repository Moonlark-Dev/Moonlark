"""每日 Note 整理测试：聊天记录匹配 → Jev 判定 wrong/expired → 删除"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from nonebot_plugin_chat.models import Note


def _note(note_id: int, content: str, keywords: str = "") -> "Note":
    from nonebot_plugin_chat.models import Note

    return Note(
        id=note_id,
        context_id="pytest_note_group",
        content=content,
        keywords=keywords,
        created_time=datetime(2026, 9, 1, 12, 0).timestamp(),
        expire_time=None,
    )


def _fake_session(messages: list[Any]) -> Any:
    return SimpleNamespace(
        session_id="pytest_note_group",
        lang_str="mlsid::--lang=zh_hans",
        processor=SimpleNamespace(openai_messages=SimpleNamespace(messages=messages)),
    )


def _choice_answer(value: str, confidence: float) -> Any:
    from nonebot_plugin_jev.types import ChoiceAnswer

    return ChoiceAnswer(choice=value, confidence=confidence)


async def test_serialize_openai_history_skips_system_and_images() -> None:
    from nonebot_plugin_chat.utils.note_manager import serialize_openai_history

    messages = [
        {"role": "system", "content": "系统提示词"},
        {"role": "user", "content": "你好呀"},
        {"role": "assistant", "content": "你好！"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "看这张图"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,xxx"}},
            ],
        },
        {"role": "tool", "content": ""},
    ]

    text = serialize_openai_history(messages)

    assert "系统提示词" not in text
    assert "[user] 你好呀" in text
    assert "[assistant] 你好！" in text
    assert "[user] 看这张图" in text
    assert "base64" not in text
    assert "[tool]" not in text


async def test_review_deletes_wrong_and_expired_notes() -> None:
    """Jev 判定 wrong/expired 且置信度足够的笔记被删除，keep 或低置信度保留"""
    from nonebot_plugin_chat.utils import note_manager as note_manager_module

    notes = [
        _note(1, "小明的生日是 8 月 15 日", keywords="小明 生日"),
        _note(2, "本周六有考试", keywords="考试"),
        _note(3, "仍然有效的笔记", keywords=""),
    ]
    deleted: list[int] = []
    fake_manager = SimpleNamespace(
        filter_note=AsyncMock(return_value=(notes, [])),
        delete_note=AsyncMock(side_effect=lambda note_id: deleted.append(note_id) or True),
    )

    answers = {
        "note_1": _choice_answer("wrong", confidence=0.9),
        "note_2": _choice_answer("expired", confidence=0.5),  # 置信度不足，不删
        "note_3": _choice_answer("keep", confidence=0.95),
    }
    captured: dict[str, Any] = {}

    async def fake_ask(state: Any, questions: dict, **kwargs: Any) -> dict:
        captured["state"] = state
        captured["questions"] = questions
        return answers

    fake_event_collector = SimpleNamespace(
        flush_pending=AsyncMock(return_value=[]),
        get_session_events=AsyncMock(
            return_value=[
                SimpleNamespace(
                    date="2026-09-29",
                    created_at=datetime(2026, 9, 29, 10, 0),
                    content='{"topics": ["生日"], "events": ["小明过了生日"]}',
                ),
            ],
        ),
    )

    session = _fake_session([{"role": "user", "content": "小明 生日 考试 都提到了"}])

    with (
        patch.object(note_manager_module, "get_context_notes", AsyncMock(return_value=fake_manager)),
        patch.object(note_manager_module, "event_collector", fake_event_collector),
        patch("nonebot_plugin_jev.ask", AsyncMock(side_effect=fake_ask)),
    ):
        deleted_count = await note_manager_module.review_session_notes(session)

    assert deleted_count == 1
    assert deleted == [1]

    # state 里包含聊天记录与事件列表
    state = captured["state"]
    assert "小明 生日 考试 都提到了" in state["chat_history"]
    assert "小明过了生日" in state["events"]
    # 每条匹配到的笔记都有一个对应的问题
    assert set(captured["questions"]) == {"note_1", "note_2", "note_3"}
    # 问题文本是本地化键引用
    question = captured["questions"]["note_1"]
    assert question.criteria.keys() == {"keep", "wrong", "expired"}


async def test_review_skips_when_no_matched_notes() -> None:
    from nonebot_plugin_chat.utils import note_manager as note_manager_module

    fake_manager = SimpleNamespace(filter_note=AsyncMock(return_value=([], [])), delete_note=AsyncMock())
    session = _fake_session([{"role": "user", "content": "任意内容"}])

    with patch.object(note_manager_module, "get_context_notes", AsyncMock(return_value=fake_manager)):
        assert await note_manager_module.review_session_notes(session) == 0

    fake_manager.delete_note.assert_not_awaited()


async def test_review_survives_jev_failure() -> None:
    """Jev 不可用时整理步骤直接跳过，不抛异常、不删笔记"""
    from nonebot_plugin_chat.utils import note_manager as note_manager_module

    notes = [_note(1, "内容", keywords="")]
    fake_manager = SimpleNamespace(
        filter_note=AsyncMock(return_value=(notes, [])),
        delete_note=AsyncMock(),
    )
    fake_event_collector = SimpleNamespace(
        flush_pending=AsyncMock(return_value=[]),
        get_session_events=AsyncMock(return_value=[]),
    )
    session = _fake_session([{"role": "user", "content": "内容"}])

    with (
        patch.object(note_manager_module, "get_context_notes", AsyncMock(return_value=fake_manager)),
        patch.object(note_manager_module, "event_collector", fake_event_collector),
        patch("nonebot_plugin_jev.ask", AsyncMock(side_effect=RuntimeError("no key"))),
    ):
        result = await note_manager_module.review_session_notes(session)

    assert result == 0
    fake_manager.delete_note.assert_not_awaited()


async def test_review_empty_history_returns_zero() -> None:
    from nonebot_plugin_chat.utils.note_manager import review_session_notes

    session = _fake_session([])
    assert await review_session_notes(session) == 0
