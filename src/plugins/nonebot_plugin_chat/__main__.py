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
import random
from datetime import datetime

from nonebot import on_message
from nonebot.adapters import Event, Bot
from nonebot.adapters.qq import Bot as Bot_QQ
from nonebot_plugin_alconna import UniMessage


from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_openai import generate_message, fetch_messages

from .models import SessionMessage, ChatUser
from .utils import get_history, generate_history, generate_memory


async def handle_qq_bot(message: str, session: async_scoped_session, user_id: str) -> None:
    pass


@on_message(priority=10, block=True).handle()
async def _(event: Event, bot: Bot, session: async_scoped_session, user_id: str = get_user_id()) -> None:
    message = event.get_plaintext()
    if not message:
        return
    elif isinstance(bot, Bot_QQ):
        await handle_qq_bot(message, session, user_id)
        return
    history = (await get_history(session, user_id)) or await generate_history(user_id, session)
    history.append(generate_message(message, "user"))
    reply = await fetch_messages(history, user_id)
    for line in reply.splitlines():
        await asyncio.sleep(random.random() / 2 * len(line))
        await UniMessage().text(line).send()
    session.add(SessionMessage(content=message, role="user", user_id=user_id))
    session.add(SessionMessage(content=reply, role="assistant", user_id=user_id))
    user_data = await session.get(ChatUser, {"user_id": user_id})
    if user_data is None:
        user_data = ChatUser(user_id=user_id, memory="None", latest_chat=datetime.now())
    await session.merge(user_data)
    await session.commit()
    if len(history) >= 25:
        asyncio.create_task(generate_memory(user_id))
