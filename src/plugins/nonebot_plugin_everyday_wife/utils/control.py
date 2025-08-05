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

from datetime import date
from typing import cast, Optional

from nonebot.internal.adapter import Message
from nonebot_plugin_orm import get_session, async_scoped_session
from sqlalchemy import select

from nonebot_plugin_everyday_wife.models import WifeData


async def marry(couple: tuple[str, str], group_id: str) -> None:
    today = date.today()
    async with get_session() as session:
        await session.merge(
            WifeData(group_id=group_id, user_id=couple[0], wife_id=couple[1], generate_date=today, queried=False)
        )
        await session.merge(
            WifeData(group_id=group_id, user_id=couple[1], wife_id=couple[0], generate_date=today, queried=False)
        )


async def divorce(group_id: str, session: async_scoped_session, platform_user_id: str) -> None:
    query = cast(
        Optional[WifeData],
        await session.scalar(
            select(WifeData).where(WifeData.user_id == platform_user_id, WifeData.group_id == group_id)
        ),
    )
    if query:
        result = await session.scalar(
            select(WifeData).where(WifeData.user_id == query.wife_id, WifeData.group_id == group_id)
        )
        if result:
            await session.delete(result)
        await session.delete(query)
    await session.commit()


def get_at_argument(message: Message) -> Optional[str]:
    for seg in message:
        if seg.type == "at":
            return seg.data["user_id"]
    return None
