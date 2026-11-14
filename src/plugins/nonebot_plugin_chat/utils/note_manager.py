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
from typing import TYPE_CHECKING, Any, List, Optional, cast

from nonebot import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_chat.types import NOTE_TYPES, NoteCheckResult, NoteType
from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_openai.utils.message import generate_message, get_messages
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..models import Note

NOTE_TYPE_EVENT: NoteType = "event"
NOTE_TYPE_BASIC_INFO: NoteType = "basic_info"
NOTE_TYPE_USER: NoteType = "user"
NOTE_TYPE_PROMPT: NoteType = "prompt"


def normalize_note_type(value: Optional[str]) -> NoteType:
    """把外部传入的记忆类型归一化，未知类型按事件处理"""
    normalized = (value or "").strip().lower()
    if normalized in NOTE_TYPES:
        return cast(NoteType, normalized)
    return NOTE_TYPE_EVENT


def parse_keywords(keywords_str: str) -> List[str]:
    """Parse keywords string, supporting both space and comma separators for backward compatibility"""
    if not keywords_str:
        return []
    # Support both space and comma separators (existing data uses space, docs mentioned comma)
    return [k.strip() for k in re.split(r"[\s,]+", keywords_str) if k.strip()]


def sanitize_keywords(keywords_str: str, subject: str) -> str:
    """去掉与中心词重复的关键词：中心词不能出现在 keywords 中

    不同笔记的中心词可以重复，但同一条笔记的 keywords 不应再包含自己的中心词，
    否则中心词会被当成普通关键词参与匹配。比较时忽略大小写，关键词包含中心词
    也视为重复（例如中心词「小明」与关键词「小明的生日」）。
    """
    normalized_subject = (subject or "").strip().lower()
    keywords = []
    for keyword in parse_keywords(keywords_str or ""):
        if normalized_subject and normalized_subject in keyword.lower():
            continue
        keywords.append(keyword)
    return " ".join(keywords)


def _term_in_chat(term: str, haystack: str) -> bool:
    normalized_term = (term or "").strip().lower()
    return bool(normalized_term) and normalized_term in haystack


def note_matches_chat(note: Note, chat_text: str, nickname: str = "") -> bool:
    """判断一条笔记是否应在本轮聊天中被召回

    「聊天中出现」包括消息文本中出现，或发送者昵称中出现。召回规则：

    - ``basic_info`` / ``prompt``：中心词出现即召回；
    - ``event``：中心词出现，或至少两个关键词出现；
    - ``user``：中心词出现且至少一个关键词出现。
    """
    haystack = f"{chat_text}\n{nickname}".lower()
    note_type = normalize_note_type(getattr(note, "type", None))
    subject_matched = _term_in_chat(getattr(note, "subject", "") or "", haystack)
    matched_keywords = {
        keyword.lower()
        for keyword in parse_keywords(getattr(note, "keywords", "") or "")
        if _term_in_chat(keyword, haystack)
    }

    if note_type in (NOTE_TYPE_BASIC_INFO, NOTE_TYPE_PROMPT):
        return subject_matched
    if note_type == NOTE_TYPE_USER:
        return subject_matched and len(matched_keywords) >= 1
    return subject_matched or len(matched_keywords) >= 2


class NoteManager:
    """Note management system for creating, reading, updating, and deleting notes"""

    def __init__(self, context_id: str):
        self.context_id = context_id  # user_id for private, group_id for groups

    async def create_note(
        self,
        content: str,
        keywords: str = "",
        expire_hours: Optional[float] = None,
        note_type: str = NOTE_TYPE_EVENT,
        subject: str = "",
        private: bool = False,
    ) -> Note:
        """
        Create a new note

        Args:
            content: The content of the note
            keywords: Space-separated keywords for the note (e.g., "keyword1 keyword2 keyword3")
            expire_hours: Number of hours until the note expires (default: 7 days = 168 hours)
            note_type: 记忆类型（event / basic_info / user / prompt）
            subject: 召回用的中心词；user / basic_info 必须为用户昵称
            private: 是否私密（私密笔记不跨会话共享）

        Returns:
            The created Note object
        """
        current_time = datetime.now()
        note_type = normalize_note_type(note_type)
        subject = (subject or "").strip()
        keywords = sanitize_keywords(keywords, subject)

        # Calculate expiration time (default 7 days = 168 hours)
        expire_time = None
        if expire_hours is not None:
            if expire_hours != -1:  # -1 means no expiration
                expire_time = current_time + timedelta(hours=expire_hours)

        async with get_session() as session:
            # basic_info 每个用户只能有一句话：同一中心词只保留一条，再次写入时直接替换
            if note_type == NOTE_TYPE_BASIC_INFO and subject:
                result = await session.scalars(
                    select(Note)
                    .where(
                        Note.context_id == self.context_id,
                        Note.type == NOTE_TYPE_BASIC_INFO,
                        Note.subject == subject,
                    )
                    .order_by(Note.created_time.asc())
                )
                existing_notes = list(result.all())
                if existing_notes:
                    note = existing_notes[0]
                    note.content = content
                    note.keywords = keywords
                    note.expire_time = expire_time
                    note.private = private
                    for extra_note in existing_notes[1:]:
                        await session.delete(extra_note)
                    await session.commit()
                    await session.refresh(note)
                    return note

            # Create the note
            note = Note(
                context_id=self.context_id,
                content=content,
                keywords=keywords,
                type=note_type,
                subject=subject,
                private=private,
                created_time=current_time.timestamp(),
                expire_time=expire_time,
            )
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
        note_type: Optional[str] = None,
        subject: Optional[str] = None,
        private: Optional[bool] = None,
    ) -> bool:
        """
        Update a note

        Args:
            note_id: The ID of the note to update
            content: New content for the note (optional)
            keywords: New keywords for the note (optional)
            expire_hours: New expiration time in hours (optional)
            note_type: New memory type for the note (optional)
            subject: New subject for the note (optional)
            private: New privacy flag for the note (optional)

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
            if note_type is not None:
                note.type = normalize_note_type(note_type)
            if subject is not None:
                note.subject = subject.strip()
            if private is not None:
                note.private = private
            if expire_hours is not None:
                current_time = datetime.now()
                if expire_hours == -1:  # No expiration
                    note.expire_time = None
                else:
                    note.expire_time = current_time + timedelta(hours=expire_hours)
            # 中心词不能出现在 keywords 中（修改中心词或关键词时都要重新清洗）
            note.keywords = sanitize_keywords(note.keywords or "", note.subject or "")

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
        return parse_keywords(keywords_str)

    async def filter_note(
        self, chat_text: str, nickname: str = "", include_expired: bool = False
    ) -> tuple[List[Note], list[Note]]:
        """按记忆类型召回当前会话与其它会话的笔记

        ``nickname`` 是发送者昵称，用于实现「聊天中出现」的第二种定义：消息文本中
        出现，或用户昵称中出现。其它会话的私密笔记永远不会跨会话召回。
        """
        notes = [note for note in await self.get_notes(include_expired) if note_matches_chat(note, chat_text, nickname)]
        notes_from_other_groups = [
            note
            for note in await self.get_notes(include_expired, except_current_context=True)
            if not note.private and note_matches_chat(note, chat_text, nickname)
        ]
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
# 每日 Note 整理（上下文重置前，交给 Decisions API 判定是否删除）
# ========================================================================

# 交给 Decisions API 的 state 中聊天记录的最大字符数（关键词匹配仍使用完整记录）
NOTE_REVIEW_CHAT_CHAR_LIMIT = 20000
# 判定为 delete 且置信度达到该值才删除笔记
NOTE_DELETE_MIN_CONFIDENCE = 0.72
# 单次审查最多提交的问题数（OpenRouter / Gemini Decision 1 上限为 1000，分批审查避免超限）
NOTE_REVIEW_BATCH_SIZE = 200


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
    """笔记的可读描述，作为判定时的题目数据"""
    created = datetime.fromtimestamp(note.created_time).strftime("%Y-%m-%d %H:%M")
    note_type = normalize_note_type(getattr(note, "type", None))
    subject = (getattr(note, "subject", "") or "").strip()
    type_text = f"类型: {note_type}" + (f"，中心词: {subject}" if subject else "")
    parts = [f"[#{note.id}] ({type_text}) {note.content}"]
    if note.keywords:
        parts.append(f"关键词: {note.keywords}")
    if getattr(note, "private", False):
        parts.append("私密")
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

    根据所选会话的整个聊天记录读出所有能被匹配到的 Note（``filter_note`` 按记忆类型
    与中心词/关键词匹配），连同该会话当天的事件列表一起交给 Decisions API 分析每条笔记是否
    应当删除（delete：内容错误、已经过期，或已被后续事件/更新的笔记取代）；判定为
    delete 且置信度足够的笔记会被删除。

    Returns:
        删除的笔记数量；无可整理内容或 Decisions API 不可用时返回 0
    """
    from nonebot_plugin_decision import ChoiceAnswer, ask, choice, lang_ref

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

    now_iso = datetime.now().isoformat(timespec="seconds")
    answers: dict[str, Any] = {}
    for start in range(0, len(matched_notes), NOTE_REVIEW_BATCH_SIZE):
        batch = matched_notes[start : start + NOTE_REVIEW_BATCH_SIZE]
        state = {
            # 关键词匹配使用完整聊天记录，交给 Decisions API 的 state 只保留尾部以控制体积
            "chat_history": chat_history[-NOTE_REVIEW_CHAT_CHAR_LIMIT:],
            "events": events_text,
            "notes": [_note_description(note) for note in batch],
            "now": now_iso,
        }
        questions = {
            f"note_{note.id}": choice(
                lang_ref("note_review.question", _note_description(note)),
                criteria={key: lang_ref(f"note_review.criteria.{key}") for key in ("keep", "delete")},
            )
            for note in batch
        }
        try:
            batch_answers = await ask(
                state,
                questions,
                lang_str=session.lang_str,
                identify="Note Review",
                session_id=session.session_id,
            )
            answers.update(batch_answers)
        except Exception as e:
            logger.warning(f"[NoteReview:{session.session_id}] 笔记审查失败: {e}")
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
