"""Note 类型化召回与中心词/关键词查重测试"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    import pytest


def _note(
    note_type: str,
    subject: str = "",
    keywords: str = "",
    private: bool = False,
    note_id: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=note_id,
        type=note_type,
        subject=subject,
        keywords=keywords,
        private=private,
        content="内容",
        created_time=0.0,
        expire_time=None,
    )


def test_normalize_note_type_falls_back_to_event() -> None:
    from nonebot_plugin_chat.utils.note_manager import normalize_note_type

    assert normalize_note_type("basic_info") == "basic_info"
    assert normalize_note_type(" USER ") == "user"
    assert normalize_note_type("unknown") == "event"
    assert normalize_note_type(None) == "event"


async def test_check_note_prompt_documents_all_note_types() -> None:
    from nonebot_plugin_openai import get_message_text

    rendered = await get_message_text("check_note/system.md.jinja", current_time="2026-11-14 22:00:00")

    for note_type in ("event", "basic_info", "user", "prompt"):
        assert f"`{note_type}`" in rendered
    assert '"subject"' in rendered
    assert '"private"' in rendered
    assert "中心词不能出现在 keywords 中" in rendered


def test_note_check_result_accepts_type_subject_private() -> None:
    from nonebot.compat import type_validate_json

    from nonebot_plugin_chat.types import NoteCheckResult

    result = type_validate_json(
        NoteCheckResult,
        '{"create": true, "type": "basic_info", "subject": "小明", "private": true,'
        ' "text": "小明是群里的大学生", "keywords": null, "expire_hours": 87600, "comment": ""}',
    )
    assert result["type"] == "basic_info"
    assert result["subject"] == "小明"
    assert result["private"] is True


def test_sanitize_keywords_removes_subject_and_substrings() -> None:
    from nonebot_plugin_chat.utils.note_manager import sanitize_keywords

    assert sanitize_keywords("小明 生日 小明的爱好 排球", "小明") == "生日 排球"
    assert sanitize_keywords("小明, 生日", "小明") == "生日"
    assert sanitize_keywords("生日", "") == "生日"


def test_basic_info_and_prompt_recall_on_subject_only() -> None:
    from nonebot_plugin_chat.utils.note_manager import note_matches_chat

    basic_info = _note("basic_info", subject="小明")
    prompt = _note("prompt", subject="称呼")

    assert note_matches_chat(basic_info, "小明今天来了") is True
    assert note_matches_chat(basic_info, "小红今天来了") is False
    assert note_matches_chat(prompt, "以后称呼我小蓝") is True
    assert note_matches_chat(prompt, "今天天气不错") is False


def test_event_recalls_on_subject_or_two_keywords() -> None:
    from nonebot_plugin_chat.utils.note_manager import note_matches_chat

    note = _note("event", subject="开黑", keywords="周六 游戏")

    assert note_matches_chat(note, "今晚开黑吗") is True
    assert note_matches_chat(note, "周六一起玩吗") is False  # 只有一个关键词
    assert note_matches_chat(note, "周六一起打游戏") is True  # 两个关键词


def test_user_recalls_on_subject_and_one_keyword() -> None:
    from nonebot_plugin_chat.utils.note_manager import note_matches_chat

    note = _note("user", subject="小明", keywords="排球 训练")

    assert note_matches_chat(note, "小明最近怎么样") is False  # 只有中心词
    assert note_matches_chat(note, "小明去训练了") is True  # 中心词 + 一个关键词
    assert note_matches_chat(note, "今天训练", nickname="小明") is True  # 昵称命中中心词
    assert note_matches_chat(note, "今天训练", nickname="小红") is False


def test_keyword_matching_is_case_insensitive() -> None:
    from nonebot_plugin_chat.utils.note_manager import note_matches_chat

    note = _note("event", subject="", keywords="Python CI")

    assert note_matches_chat(note, "python 和 ci 都挂了") is True


async def test_filter_note_skips_private_notes_from_other_contexts() -> None:
    from nonebot_plugin_chat.utils.note_manager import NoteManager

    manager = NoteManager("current")
    same_context = [_note("event", subject="开黑", note_id=1)]
    other_context = [
        _note("event", subject="开黑", private=False, note_id=2),
        _note("event", subject="开黑", private=True, note_id=3),
    ]

    async def fake_get_notes(_include_expired: bool = False, except_current_context: bool = False):
        return other_context if except_current_context else same_context

    with patch.object(manager, "get_notes", AsyncMock(side_effect=fake_get_notes)):
        notes, other_notes = await manager.filter_note("今晚开黑")

    assert [note.id for note in notes] == [1]
    assert [note.id for note in other_notes] == [2]


async def test_apply_pending_note_goes_through_check_note() -> None:
    from nonebot_plugin_chat.utils.tool_manager import ToolManager

    session = SimpleNamespace(
        session_id="pytest_pending_note",
        text=AsyncMock(side_effect=lambda key, *_args: key),
        get_users=AsyncMock(return_value={"小明": "10001"}),
    )
    processor = SimpleNamespace(
        session=session,
        pending_notes={0: {"content": "候选内容", "keywords": "候选关键词", "expire_hours": 12}},
    )
    manager = ToolManager(processor)  # type: ignore[arg-type]
    note_manager = SimpleNamespace(create_note=AsyncMock())

    checked = {
        "create": True,
        "type": "user",
        "subject": "小明",
        "private": True,
        "text": "整理后的内容",
        "keywords": "生日",
        "expire_hours": 24,
        "comment": "",
    }

    with (
        patch("nonebot_plugin_chat.utils.tool_manager.check_note", AsyncMock(return_value=checked)) as check_mock,
        patch("nonebot_plugin_chat.utils.tool_manager.get_context_notes", AsyncMock(return_value=note_manager)),
    ):
        result = await manager.apply_pending_note(0)

    check_mock.assert_awaited_once_with(session, "候选关键词", "候选内容", 12)
    note_manager.create_note.assert_awaited_once_with(
        content="整理后的内容",
        keywords="生日",
        expire_hours=24,
        note_type="user",
        subject="小明",
        private=True,
    )
    assert processor.pending_notes == {}
    assert result == "pending_note.applied"


async def test_apply_pending_note_keeps_note_when_check_rejects() -> None:
    from nonebot_plugin_chat.utils.tool_manager import ToolManager

    session = SimpleNamespace(
        session_id="pytest_pending_note",
        text=AsyncMock(side_effect=lambda key, *_args: key),
    )
    processor = SimpleNamespace(
        session=session,
        pending_notes={0: {"content": "候选内容"}},
    )
    manager = ToolManager(processor)  # type: ignore[arg-type]
    note_manager = SimpleNamespace(create_note=AsyncMock())

    with (
        patch(
            "nonebot_plugin_chat.utils.tool_manager.check_note",
            AsyncMock(return_value={"create": False, "comment": "没有价值"}),
        ),
        patch("nonebot_plugin_chat.utils.tool_manager.get_context_notes", AsyncMock(return_value=note_manager)),
    ):
        result = await manager.apply_pending_note(0)

    note_manager.create_note.assert_not_awaited()
    assert 0 in processor.pending_notes
    assert result == "note.not_create"


async def test_create_basic_info_replaces_same_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from nonebot_plugin_chat.models import Note
    from nonebot_plugin_chat.utils import note_manager as note_manager_module

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Note.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(note_manager_module, "get_session", lambda: factory())

    manager = note_manager_module.NoteManager("pytest_basic_info")
    first = await manager.create_note(
        "小明是学生",
        keywords="小明 学生",
        note_type="basic_info",
        subject="小明",
        private=True,
    )
    second = await manager.create_note("小明是大学生", note_type="basic_info", subject="小明")

    notes = await manager.get_notes()
    await engine.dispose()

    assert len(notes) == 1
    assert first.id == second.id == notes[0].id
    assert notes[0].content == "小明是大学生"
    assert notes[0].keywords == ""
    assert notes[0].type == "basic_info"
    assert notes[0].subject == "小明"
    assert notes[0].private is False


async def test_apply_pending_note_rejects_non_nickname_subject() -> None:
    from nonebot_plugin_chat.utils.tool_manager import ToolManager

    session = SimpleNamespace(
        session_id="pytest_pending_note",
        text=AsyncMock(side_effect=lambda key, *_args: key),
        get_users=AsyncMock(return_value={"小明": "10001"}),
    )
    processor = SimpleNamespace(session=session, pending_notes={0: {"content": "候选内容"}})
    manager = ToolManager(processor)  # type: ignore[arg-type]
    note_manager = SimpleNamespace(create_note=AsyncMock())

    checked = {
        "create": True,
        "type": "user",
        "subject": "小红",
        "private": False,
        "text": "整理后的内容",
        "keywords": None,
        "expire_hours": 24,
        "comment": "",
    }

    with (
        patch("nonebot_plugin_chat.utils.tool_manager.check_note", AsyncMock(return_value=checked)),
        patch("nonebot_plugin_chat.utils.tool_manager.get_context_notes", AsyncMock(return_value=note_manager)),
    ):
        result = await manager.apply_pending_note(0)

    note_manager.create_note.assert_not_awaited()
    assert 0 in processor.pending_notes
    assert result == "note.subject_not_user"
