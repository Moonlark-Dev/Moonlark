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
import asyncio
from datetime import datetime
from typing import Optional

from nonebot import Bot
from nonebot.internal.adapter import Event
from nonebot_plugin_alconna.uniseg import reply_fetch
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select, func

from ...models import CommentData
from .message import get_cave_by_message_id

lock = asyncio.Lock()


async def get_belong_cave(bot: Bot, event: Event) -> Optional[int]:
    reply = await reply_fetch(event, bot)
    if reply is None:
        return None
    return get_cave_by_message_id(reply.id)


async def get_message(event: Event) -> str:
    return event.get_plaintext()


async def get_comment_id(session: async_scoped_session) -> int:
    result = await session.scalar(select(func.max(CommentData.id)))
    return (result + 1) if result is not None else 0


async def post(user_id: str, session: async_scoped_session, content: str, belong: int) -> int:
    async with lock:
        comment_id = await get_comment_id(session)
        session.add(CommentData(id=comment_id, author=user_id, content=content, time=datetime.now(), belong=belong))
        await session.commit()
    return comment_id
