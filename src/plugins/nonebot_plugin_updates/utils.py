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

from nonebot import require

require("nonebot_plugin_orm")
from nonebot_plugin_orm import get_session  # noqa: E402

from .models import UpdateReadStatus  # noqa: E402
from .store import load_announcement  # noqa: E402


async def has_new_update(user_id: str) -> bool:
    """判断用户是否有未阅读的最新更新公告"""
    announcement = await load_announcement()
    if announcement is None:
        return False
    async with get_session() as session:
        data = await session.get(UpdateReadStatus, user_id)
    return data is None or data.last_update_id != announcement.update_id


async def mark_update_read(user_id: str) -> None:
    """将最新更新公告标记为已阅读"""
    announcement = await load_announcement()
    if announcement is None:
        return
    async with get_session() as session:
        data = await session.get(UpdateReadStatus, user_id)
        if data is None:
            session.add(UpdateReadStatus(user_id=user_id, last_update_id=announcement.update_id))
        elif data.last_update_id != announcement.update_id:
            data.last_update_id = announcement.update_id
        else:
            return
        await session.commit()
