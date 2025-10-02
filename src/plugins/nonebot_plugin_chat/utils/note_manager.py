#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
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
from typing import List, Optional

from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..models import Note


class NoteManager:
    """Note management system for creating, reading, updating, and deleting notes"""

    def __init__(self, context_id: str):
        self.context_id = context_id  # user_id for private, group_id for groups

    async def create_note(self, content: str, keywords: str = "", expire_days: Optional[int] = None) -> Note:
        """
        Create a new note

        Args:
            content: The content of the note
            keywords: Comma-separated keywords for the note
            expire_days: Number of days until the note expires (default: 7 days)

        Returns:
            The created Note object
        """
        current_time = datetime.now()

        # Calculate expiration time (default 7 days)
        expire_time = None
        if expire_days is not None:
            if expire_days != -1:  # -1 means no expiration
                expire_time = current_time + timedelta(days=expire_days)

        # Create the note
        note = Note(
            context_id=self.context_id,
            content=content,
            keywords=keywords,
            created_time=current_time,
            expire_time=expire_time,
            hash_value=hash(f"{self.context_id}:{content}:{keywords}:{current_time}"),
        )

        # Save to database
        async with get_session() as session:
            session.add(note)
            await session.commit()
            await session.refresh(note)

        return note

    async def get_notes(self, include_expired: bool = False) -> List[Note]:
        """
        Get all notes for this context

        Args:
            include_expired: Whether to include expired notes

        Returns:
            List of Note objects
        """
        async with get_session() as session:
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
        expire_days: Optional[int] = None,
    ) -> bool:
        """
        Update a note

        Args:
            note_id: The ID of the note to update
            content: New content for the note (optional)
            keywords: New keywords for the note (optional)
            expire_days: New expiration time in days (optional)

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
            if expire_days is not None:
                current_time = datetime.now()
                if expire_days == -1:  # No expiration
                    note.expire_time = None
                else:
                    note.expire_time = current_time + timedelta(days=expire_days)

            # Update hash and last modified time
            note.hash_value = hash(f"{note.context_id}:{note.content}:{note.keywords}:{note.created_time}")

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

    async def filter_note(
        self, chat_history: str, memory_topics: list[str], include_expired: bool = False
    ) -> List[Note]:
        """
        Get notes that match any of the provided keywords

        Args:
            keywords: List of keywords to search for
            include_expired: Whether to include expired notes

        Returns:
            List of Note objects that match the keywords
        """
        notes = []
        for note in await self.get_notes(include_expired):
            if not note.keywords:
                notes.append(note)
                continue
            keywords = note.keywords.split(" ")
            for keyword in keywords:
                if keyword in chat_history or keyword in memory_topics:
                    notes.append(note)
                    break
        return notes


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
