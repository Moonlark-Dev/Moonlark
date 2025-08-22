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
from datetime import datetime

from nonebot_plugin_orm import async_scoped_session, AsyncSession, get_session
from sqlalchemy import select

from nonebot_plugin_openai.types import Messages
from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_openai.utils.message import generate_message

from ..lang import lang
from ..models import SessionMessage, ChatUser


def generate_message_string(messages: Messages) -> str:
    m = []
    for msg in messages:
        if msg["role"] != "system":
            m.append(f"- {msg['role']}: {msg['content']}")
    return "\n".join(m)


async def get_history(session: async_scoped_session | AsyncSession, user_id: str) -> Messages:
    messages = []
    for message in await session.scalars(
        select(SessionMessage).where(SessionMessage.user_id == user_id).order_by(SessionMessage.id_)
    ):
        messages.append(generate_message(message.content, message.role))
    return messages


async def get_memory(user_id: str, session: async_scoped_session | AsyncSession) -> str:
    result = await session.get(ChatUser, {"user_id": user_id})
    if result:
        return result.memory
    return "None"


async def generate_history(user_id: str, session: async_scoped_session) -> Messages:
    text = await lang.text("prompt.default", user_id, await get_memory(user_id, session))
    session.add(SessionMessage(user_id=user_id, content=text, role="system"))
    return [generate_message(text, "system")]


async def generate_memory(user_id: str) -> None:
    async with get_session() as session:
        messages = await get_history(session, user_id)
        message_string = generate_message_string(messages)
        memory = await fetch_message(
            [
                generate_message(
                    await lang.text("prompt.memory", user_id, await get_memory(user_id, session)), "system"
                ),
                generate_message(await lang.text("prompt.memory_2", user_id, message_string, "user")),
            ]
        )
        user_data = await session.get(ChatUser, {"user_id": user_id})
        if user_data is None:
            user_data = ChatUser(user_id=user_id, memory="None", latest_chat=datetime.now())
        user_data.memory = memory
        await session.merge(user_data)
        for message in await session.scalars(
            select(SessionMessage).where(SessionMessage.user_id == user_id).order_by(SessionMessage.id_)
        ):
            await session.delete(message)
        await session.commit()
