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

import random

from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from ..lang import lang
from ..models import CaveData
from .comment import get_comments, add_cave_message
from .cool_down import on_use
from .decoder import decode_cave


async def get_cave(session: async_scoped_session) -> CaveData:
    cave_id_list = (await session.scalars(select(CaveData.id).where(CaveData.public))).all()
    cave_id = random.choice(cave_id_list)
    return await session.get_one(CaveData, {"id": cave_id})


async def send_cave(session: async_scoped_session, user_id: str, group_id: str, reverse: bool = False) -> None:
    try:
        cave_data = await get_cave(session)
        cave_id = cave_data.id
        content = await decode_cave(cave_data, session, user_id, cave_id == 398 or reverse)
    except NoResultFound:
        await lang.finish("cave.noresult", user_id)
    except IndexError:
        await lang.finish("cave.nocave", user_id)
    cave_message = await content.send()
    if msg := await get_comments(cave_id, session, user_id):
        await msg.send()
    await on_use(user_id, session)
    try:
        add_cave_message(cave_id, str(cave_message.msg_ids[0]["message_id"]))
    except TypeError:
        # Ignore exception mentioned in issue 325, which is caused by f**king QQ
        pass
