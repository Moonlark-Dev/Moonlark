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

import datetime
import random

from nonebot_plugin_orm import AsyncSession, async_scoped_session
from sqlalchemy import func, select
from sqlalchemy.exc import NoResultFound

from ..lang import lang
from ..models import CaveData
from .comment import add_cave_message, get_comments
from .cool_down import on_use
from .decoder import decode_cave

THURSDAY_KEYWORDS = ("星期四", "50", "KFC")


async def _random_keyword_cave(session: async_scoped_session | AsyncSession, require_keywords: bool | None = None) -> CaveData | None:
    stmt = select(CaveData).where(CaveData.public)
    if require_keywords is not None:
        for kw in THURSDAY_KEYWORDS:
            condition = CaveData.content.ilike(f"%{kw}%")
            stmt = stmt.where(condition if require_keywords else ~condition)
    result = await session.execute(stmt.order_by(func.random()).limit(1))
    return result.scalar_one_or_none()


async def get_cave(session: async_scoped_session | AsyncSession) -> CaveData:
    is_thursday = datetime.datetime.now().weekday() == 3

    if is_thursday:
        if random.random() < 0.4:
            cave = await _random_keyword_cave(session, require_keywords=True)
            if cave is None:
                cave = await _random_keyword_cave(session, require_keywords=False)
        else:
            cave = await _random_keyword_cave(session, require_keywords=False)
            if cave is None:
                cave = await _random_keyword_cave(session, require_keywords=True)
        if cave is None:
            raise NoResultFound
        return cave
    cave = await _random_keyword_cave(session)
    if cave is None:
        raise IndexError
    contains_any = any(kw.lower() in cave.content.lower() for kw in THURSDAY_KEYWORDS)
    if contains_any and random.random() < 0.5:
        cave = await _random_keyword_cave(session) or cave
    return cave


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
