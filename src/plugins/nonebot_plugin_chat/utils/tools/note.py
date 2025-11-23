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

import time
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Optional

from ...utils.note_manager import get_context_notes


def get_note_poster(context_id: str) -> Callable[[str, Optional[int], Optional[str]], Awaitable[str]]:
    async def push_note(text: str, expire_days: Optional[int] = None, keywords: Optional[str] = None) -> str:
        """
        Push a new note to the note system.

        Args:
            text: The content of the note
            context_id: The context ID (user_id for private, group_id for groups)
            expire_days: Number of days until the note expires (default: 7 days, -1 for no expiration)
            keywords: Comma-separated keywords for the note

        Returns:
            A confirmation message
        """
        # Get the note manager for this context
        note_manager = await get_context_notes(context_id)

        # Create the note
        note = await note_manager.create_note(content=text, keywords=keywords or "", expire_days=expire_days or 3650)

        # Return a confirmation message
        created_time = datetime.fromtimestamp(note.created_time).strftime("%Y-%m-%d %H:%M:%S")
        if note.expire_time:
            expire_time = note.expire_time.strftime("%Y-%m-%d %H:%M:%S")
            return f"Note created successfully at {created_time}, will expire at {expire_time}."
        else:
            return f"Note created successfully at {created_time} with no expiration."

    return push_note
