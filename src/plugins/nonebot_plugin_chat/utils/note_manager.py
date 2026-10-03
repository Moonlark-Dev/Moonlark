#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

from datetime import datetime, timedelta
import json
import re
from typing import TYPE_CHECKING, Any, List, Optional

from nonebot import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_chat.types import AvailableNote, NoteCheckResult
from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_openai.utils.message import generate_message, get_messages
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..models import Note


class NoteManager:
    """Note management system for creating, reading, updating, and deleting notes"""

    def __init__(self, context_id: str):
        self.context_id = context_id  # user_id for private, group_id for groups

    async def create_note(self, content: str, keywords: str = "", expire_hours: Optional[float] = None) -> Note:
        """
        Create a new note

        Args:
            content: The content of the note
            keywords: Space-separated keywords for the note (e.g., "keyword1 keyword2 keyword3")
            expire_hours: Number of hours until the note expires (default: 7 days = 168 hours)

        Returns:
            The created Note object
        """
        current_time = datetime.now()

        # Calculate expiration time (default 7 days = 168 hours)
        expire_time = None
        if expire_hours is not None:
            if expire_hours != -1:  # -1 means no expiration
                expire_time = current_time + timedelta(hours=expire_hours)

        # Create the note
        note = Note(
            context_id=self.context_id,
            content=content,
            keywords=keywords,
            created_time=current_time.timestamp(),
            expire_time=expire_time,
        )

        # Save to database
        async with get_session() as session:
            session.add(note)
            await session.commit()
            await session.refresh(note)

        return note

    async def get_notes(self, include_expired: bool = False, except_current_context: bool = False) -> List[Note]:
        """
        Get all notes for this context

        Args:
            include_expired: Whether to include expired notes

        Returns:
            List of Note objects
        """
        async with get_session() as session:
            if except_current_context:
                query = select(Note).where(Note.context_id != self.context_id)
            else:
                query = select(Note).where(Note.context_id == self.context_id)

            # Filter out expired notes unless explicitly requested
            if not include_expired:
                current_time = datetime.now()
                query = query.where((Note.expire_time.is_(None)) | (Note.expire_time > current_time))

            result = await session.scalars(query)
            return list(result.all())

    async def get_note_by_id(self, note_id: int) -> Optional[Note]:
        """
        Get a specific note by its ID

        Args:
            note_id: The ID of the note to retrieve

        Returns:
            The Note object if found, None otherwise
        """
        async with get_session() as session:
            query = select(Note).where(Note.id == note_id, Note.context_id == self.context_id)
            result = await session.scalars(query)
            return result.first()

    async def update_note(
        self,
        note_id: int,
        content: Optional[str] = None,
        keywords: Optional[str] = None,
        expire_hours: Optional[float] = None,
    ) -> bool:
        """
        Update a note

        Args:
            note_id: The ID of the note to update
            content: New content for the note (optional)
            keywords: New keywords for the note (optional)
            expire_hours: New expiration time in hours (optional)

        Returns:
            True if the note was updated, False if not found
        """
        async with get_session() as session:
            note = await session.get(Note, note_id)
            if not note or note.context_id != self.context_id:
                return False

            # Update fields if provided
            if content is not None:
                note.content = content
            if keywords is not None:
                note.keywords = keywords
            if expire_hours is not None:
                current_time = datetime.now()
                if expire_hours == -1:  # No expiration
                    note.expire_time = None
                else:
                    note.expire_time = current_time + timedelta(hours=expire_hours)

            await session.commit()
            return True

    async def delete_note(self, note_id: int) -> bool:
        """
        Delete a note

        Args:
            note_id: The ID of the note to delete

        Returns:
            True if the note was deleted, False if not found
        """
        async with get_session() as session:
            note = await session.get(Note, note_id)
            if not note or note.context_id != self.context_id:
                return False

            await session.delete(note)
            await session.commit()
            return True

    async def delete_expired_notes(self) -> int:
        """
        Delete all expired notes for this context

        Returns:
            Number of notes deleted
        """
        current_time = datetime.now()
        deleted_count = 0

        async with get_session() as session:
            # Find expired notes
            query = select(Note).where(
                Note.context_id == self.context_id, Note.expire_time.is_not(None), Note.expire_time <= current_time
            )
            result = await session.scalars(query)
            expired_notes = result.all()

            # Delete expired notes
            for note in expired_notes:
                await session.delete(note)
                deleted_count += 1

            if deleted_count > 0:
                await session.commit()

        return deleted_count

    def _parse_keywords(self, keywords_str: str) -> List[str]:
        """Parse keywords string, supporting both space and comma separators for backward compatibility"""
        if not keywords_str:
            return []
        # Support both space and comma separators (existing data uses space, docs mentioned comma)
        return [k.strip() for k in re.split(r"[\s,]+", keywords_str) if k.strip()]

    async def filter_note(self, chat_history: str, include_expired: bool = False) -> tuple[List[Note], list[Note]]:
        notes = []
        for note in await self.get_notes(include_expired):
            if not note.keywords:
                notes.append(note)
                continue
            keywords = self._parse_keywords(note.keywords)
            for keyword in keywords:
                if keyword in chat_history:
                    notes.append(note)
                    break
        notes_from_other_groups = []
        for note in await self.get_notes(include_expired, except_current_context=True):
            if not note.keywords:
                continue
            keywords = self._parse_keywords(note.keywords)
            for keyword in keywords:
                if keyword in chat_history:
                    notes_from_other_groups.append(note)
                    break
        return notes, notes_from_other_groups


# Helper function to get notes for a context
async def get_context_notes(context_id: str) -> NoteManager:
    """
    Get a NoteManager instance for a specific context

    Args:
        context_id: The context ID (user_id for private, group_id for groups)

    Returns:
        NoteManager instance
    """
    return NoteManager(context_id)


# Helper function to clean up expired notes across all contexts
async def cleanup_expired_notes() -> int:
    """
    Delete all expired notes across all contexts

    Returns:
        Number of notes deleted
    """
    current_time = datetime.now()
    deleted_count = 0

    async with get_session() as session:
        # Find all expired notes
        query = select(Note).where(Note.expire_time.is_not(None), Note.expire_time <= current_time)
        result = await session.scalars(query)
        expired_notes = result.all()

        # Delete expired notes
        for note in expired_notes:
            await session.delete(note)
            deleted_count += 1

        if deleted_count > 0:
            await session.commit()

    return deleted_count


if TYPE_CHECKING:
    from ..core.session.base import BaseSession
    from ..models import SessionEvent

from nonebot_plugin_openai import fetch_json

from ..core.ego.event_collector import event_collector, format_event_content


async def check_note(
    session: "BaseSession", keywords: Optional[str], text: str, expire_hours: Optional[float]
) -> NoteCheckResult:
    return await fetch_json(
        await get_messages(
            "check_note",
            messages=await session.get_cached_messages_string(),
            keywords=keywords or "",
            content=text,
            expire_time=(datetime.now() + timedelta(hours=expire_hours or 87600)).isoformat(),  # 默认10年
        ),
        NoteCheckResult,  # type: ignore
        identify="Check Note",
    )


# ========================================================================
# 每日 Note 整理（上下文重置前，交给 Jev 判定是否删除）
# ========================================================================

# 交给 Jev 的 state 中聊天记录的最大字符数（关键词匹配仍使用完整记录）
NOTE_REVIEW_CHAT_CHAR_LIMIT = 20000
# Jev 判定为 delete 且置信度达到该值才删除笔记
NOTE_DELETE_MIN_CONFIDENCE = 0.72


def _content_to_text(content: Any) -> str:
    """把 OpenAI 消息的 content（字符串或分段列表）拍平成纯文本，跳过图片等非文本分段"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    parts.append(str(part.get("text", "")))
            else:
                text = getattr(part, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def serialize_openai_history(messages: list) -> str:
    """把会话的消息队列序列化为整段聊天记录（跳过 system 提示词与图片）"""
    lines = []
    for message in messages:
        if isinstance(message, dict):
            role = message.get("role", "")
            content = message.get("content")
        else:
            role = getattr(message, "role", "")
            content = getattr(message, "content", None)
        if role == "system":
            continue
        text = _content_to_text(content).strip()
        if not text:
            continue
        lines.append(f"[{role}] {text}")
    return "\n".join(lines)


def _note_description(note: Note) -> str:
    """笔记的可读描述，作为 Jev 判定时的题目数据"""
    created = datetime.fromtimestamp(note.created_time).strftime("%Y-%m-%d %H:%M")
    parts = [f"[#{note.id}] {note.content}"]
    if note.keywords:
        parts.append(f"关键词: {note.keywords}")
    parts.append(f"创建于 {created}")
    if note.expire_time:
        parts.append(f"过期时间: {note.expire_time.strftime('%Y-%m-%d %H:%M')}")
    return "；".join(parts)


def _format_events_for_review(events: list["SessionEvent"]) -> str:
    """把会话当天的事件记录格式化为可读文本（对异常内容做兜底）"""
    lines = []
    for event in events:
        time_str = f"{event.date} {event.created_at.strftime('%H:%M')}" if event.created_at else event.date
        lines.append(f"[{time_str}] {format_event_content(event.content)}")
    return "\n".join(lines)


async def review_session_notes(session: "BaseSession") -> int:
    """每天聊天上下文重置前的 Note 整理

    根据所选会话的整个聊天记录读出所有能被匹配到的 Note（``filter_note`` 关键词匹配，
    含无关键词的常驻笔记），连同该会话当天的事件列表一起交给 Jev 分析每条笔记是否
    应当删除（delete：内容错误、已经过期，或已被后续事件/更新的笔记取代）；判定为
    delete 且置信度足够的笔记会被删除。

    Returns:
        删除的笔记数量；无可整理内容或 Jev 不可用时返回 0
    """
    from nonebot_plugin_jev import ChoiceAnswer, ask, choice, lang_ref

    chat_history = serialize_openai_history(session.processor.openai_messages.messages)
    if not chat_history.strip():
        return 0

    note_manager = await get_context_notes(session.session_id)
    # include_expired=True：把所有仍存在的笔记都纳入整理（按时间过期的由每日清理任务处理）
    matched_notes, _ = await note_manager.filter_note(chat_history, include_expired=True)
    if not matched_notes:
        return 0

    # 事件列表：重置发生在凌晨 4 点，get_session_events 默认取「前一天 0:00 至今」，
    # 正好覆盖被重置的这段会话；必要时先补齐尚未生成事件的消息
    try:
        await event_collector.flush_pending(min_pending=0)
    except Exception as e:
        logger.warning(f"[NoteReview:{session.session_id}] 补齐事件失败: {e}")
    events = await event_collector.get_session_events(session.session_id)
    events_text = _format_events_for_review(events)

    state = {
        # 关键词匹配使用完整聊天记录，交给 Jev 的 state 只保留尾部以控制体积
        "chat_history": chat_history[-NOTE_REVIEW_CHAT_CHAR_LIMIT:],
        "events": events_text,
        "notes": [_note_description(note) for note in matched_notes],
        "now": datetime.now().isoformat(timespec="seconds"),
    }
    questions = {
        f"note_{note.id}": choice(
            lang_ref("note_review.question", _note_description(note)),
            criteria={key: lang_ref(f"note_review.criteria.{key}") for key in ("keep", "delete")},
        )
        for note in matched_notes
    }

    try:
        answers = await ask(state, questions, lang_str=session.lang_str, identify="Note Review")
    except Exception as e:
        logger.warning(f"[NoteReview:{session.session_id}] Jev 审查失败: {e}")
        return 0

    deleted = 0
    for note in matched_notes:
        answer = answers.get(f"note_{note.id}")
        if not isinstance(answer, ChoiceAnswer):
            continue
        if answer.choice == "delete" and answer.confidence >= NOTE_DELETE_MIN_CONFIDENCE:
            if await note_manager.delete_note(note.id):
                deleted += 1
                logger.info(
                    f"[NoteReview:{session.session_id}] 删除笔记 #{note.id}"
                    f"（置信度 {answer.confidence:.2f}）: {note.content[:50]}"
                )
    return deleted


@scheduler.scheduled_job("cron", hour="3", id="cleanup_expired_notes")
async def _() -> None:
    """Daily cleanup of expired notes at 3 AM"""
    deleted_count = await cleanup_expired_notes()
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} expired notes")
