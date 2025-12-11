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

import json
import re
from ...lang import lang
from nonebot_plugin_openai import generate_message, fetch_message
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Awaitable, Callable, Literal, Optional, TypedDict

from ...utils.note_manager import get_context_notes

if TYPE_CHECKING:
    from ...matcher.group import GroupSession


class AvailableNote(TypedDict):
    create: Literal[True]
    text: str
    expire_days: int
    keywords: Optional[str]
    comment: str


class InvalidNote(TypedDict):
    create: Literal[False]
    comment: str


NoteCheckResult = AvailableNote | InvalidNote


def decode_check_result(data: str) -> NoteCheckResult:
    return json.loads(re.sub(r"`{1,3}([a-zA-Z0-9]+)?", data, ""))


def get_note_poster(session: "GroupSession") -> Callable[[str, Optional[int], Optional[str]], Awaitable[str]]:
    context_id = session.group_id

    async def push_note(text: str, expire_days: Optional[int] = None, keywords: Optional[str] = None) -> str:
        # Get the note manager for this context
        note_manager = await get_context_notes(context_id)

        try:
            note_check_result: NoteCheckResult = decode_check_result(
                await fetch_message(
                    [
                        generate_message(
                            await lang.text("note.system", session.user_id, datetime.now().isoformat()), "system"
                        ),
                        generate_message(
                            await lang.text(
                                "note.message",
                                session.user_id,
                                await session.get_cached_messages_string(),
                                keywords or "",
                                text,
                                (datetime.now() + timedelta(days=expire_days or 3650)).isoformat(),
                            ),
                            "user",
                        ),
                    ]
                )
            )
        except json.JSONDecodeError:
            note_check_result = AvailableNote(
                create=True, keywords=keywords, expire_days=expire_days or 3650, text=text, comment=""
            )
        if note_check_result["create"] == False:
            return await lang.text("note.not_create", session.user_id, note_check_result["comment"])
        text = note_check_result["text"]
        keywords = note_check_result["keywords"]
        expire_days = note_check_result["expire_days"]

        # Create the note
        note = await note_manager.create_note(content=text, keywords=keywords or "", expire_days=expire_days or 3650)

        return await lang.text("note.create", session.user_id)

    return push_note
