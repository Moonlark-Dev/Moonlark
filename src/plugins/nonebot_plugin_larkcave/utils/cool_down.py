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

from nonebot_plugin_orm import async_scoped_session
from sqlalchemy.exc import NoResultFound

from ..config import config
from ..models import GroupData, UserCoolDownData


async def is_group_cooled(
    group_id: str, session: async_scoped_session, is_public_bot: bool = False
) -> tuple[bool, float]:
    try:
        data = await session.get_one(GroupData, {"group_id": group_id})
    except NoResultFound:
        return True, 0
    if is_public_bot:
        group_cd = timedelta(minutes=data.cool_down_time // 2)
    else:
        group_cd = timedelta(minutes=data.cool_down_time)
    remain = (group_cd - (datetime.now() - data.last_use)).total_seconds()
    return remain <= 0, remain


async def on_group_use(group_id: str, session: async_scoped_session) -> None:
    try:
        data = await session.get_one(GroupData, {"group_id": group_id})
    except NoResultFound:
        session.add(GroupData(group_id=group_id, last_use=datetime.now()))
    else:
        data.last_use = datetime.now()
    await session.commit()


async def is_user_cooled(
    user_id: str, session: async_scoped_session, is_public_bot: bool = False
) -> tuple[bool, float]:
    try:
        data = await session.get_one(UserCoolDownData, {"user_id": user_id})
    except NoResultFound:
        return True, 0
    if is_public_bot:
        user_cd = timedelta(minutes=config.cave_user_cd // 2)
    else:
        user_cd = timedelta(minutes=config.cave_user_cd)
    remain = (user_cd - (datetime.now() - data.last_use)).total_seconds()
    return remain <= 0, remain


async def on_user_use(user_id: str, session: async_scoped_session) -> None:
    try:
        data = await session.get_one(UserCoolDownData, {"user_id": user_id})
    except NoResultFound:
        session.add(UserCoolDownData(user_id=user_id, last_use=datetime.now()))
    else:
        data.last_use = datetime.now()
    await session.commit()


async def on_use(group_id: str, user_id: str, session: async_scoped_session) -> None:
    await on_group_use(group_id, session)
    await on_user_use(user_id, session)


async def set_cool_down(group_id: str, time: float, session: async_scoped_session) -> None:
    try:
        data = await session.get_one(GroupData, {"group_id": group_id})
    except NoResultFound:
        session.add(GroupData(group_id=group_id, cool_down_time=time))
    else:
        data.cool_down_time = time
    await session.commit()
