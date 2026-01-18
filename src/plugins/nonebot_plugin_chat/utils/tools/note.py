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

from pydantic import BaseModel, Field
from ...lang import lang
from nonebot_plugin_openai import generate_message, fetch_message
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Awaitable, Callable, Literal, Optional, Union

from ...utils.note_manager import get_context_notes

if TYPE_CHECKING:
    from ...matcher.group import GroupSession


class AvailableNote(BaseModel):
    """表示一个有效的备忘录创建请求"""

    create: Literal[True] = Field(description="是否创建备忘录，此时为 True")
    text: str = Field(description="备忘录的内容")
    expire_days: int = Field(description="备忘录的过期天数")
    keywords: Optional[str] = Field(default=None, description="用于搜索的关键词")
    comment: str = Field(default="", description="对此次操作的评论或说明")


class InvalidNote(BaseModel):
    """表示一个无效的备忘录创建请求"""

    create: Literal[False] = Field(description="是否创建备忘录，此时为 False")
    comment: str = Field(description="不创建备忘录的原因说明")


class NoteCheckResult(BaseModel):
    """备忘录检查结果，包含一个有效或无效的备忘录"""

    result: Union[AvailableNote, InvalidNote] = Field(discriminator="create", description="备忘录检查结果")


def get_note_poster(session: "GroupSession") -> Callable[[str, Optional[int], Optional[str]], Awaitable[str]]:
    context_id = session.group_id

    async def push_note(text: str, expire_days: Optional[int] = None, keywords: Optional[str] = None) -> str:
        # Get the note manager for this context
        note_manager = await get_context_notes(context_id)

        # 使用结构化输出获取备忘录检查结果
        note_check_result = await fetch_message(
            [
                generate_message(await lang.text("note.system", session.user_id, datetime.now().isoformat()), "system"),
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
            ],
            response_format=NoteCheckResult,
        )

        result = note_check_result.result
        if isinstance(result, InvalidNote):
            return await lang.text("note.not_create", session.user_id, result.comment)

        # result is AvailableNote
        text = result.text
        keywords = result.keywords
        expire_days = result.expire_days

        # Create the note
        await note_manager.create_note(content=text, keywords=keywords or "", expire_days=expire_days or 3650)

        return await lang.text("note.create", session.user_id)

    return push_note


def get_note_remover(session: "GroupSession") -> Callable[[int], Awaitable[str]]:
    context_id = session.group_id

    async def remove_note(note_id: int) -> str:
        # Get the note manager for this context
        note_manager = await get_context_notes(context_id)

        # Try to delete the note
        success = await note_manager.delete_note(note_id)

        if success:
            return await lang.text("note.remove_success", session.user_id, note_id)
        else:
            return await lang.text("note.remove_not_found", session.user_id, note_id)

    return remove_note
