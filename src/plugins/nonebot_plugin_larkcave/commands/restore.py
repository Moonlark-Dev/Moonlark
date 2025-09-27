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

from nonebot_plugin_larkcave.lang import lang
from nonebot_plugin_larkcave.models import CaveData, RemovedCave
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_larkutils import get_user_id, is_user_superuser
from nonebot_plugin_larkcave.__main__ import cave
from sqlalchemy.exc import NoResultFound


@cave.assign("restore.cave_id")
async def _(
    session: async_scoped_session, cave_id: int, user_id: str = get_user_id(), is_superuser: bool = is_user_superuser()
) -> None:
    try:
        data = await session.get_one(RemovedCave, {"id": cave_id})
        cave_data = await session.get_one(CaveData, {"id": cave_id})
    except NoResultFound:
        await lang.finish("restore.not_found", user_id, cave_id)
        return
    if not ((user_id == cave_data.author and not data.superuser) or is_superuser):
        await lang.finish("restore.no_permission", user_id)
        await cave.finish()
    await session.delete(data)
    await session.commit()
    cave_data.public = True
    await session.commit()
    await lang.finish("restore.success", user_id, cave_id)
