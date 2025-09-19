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

import traceback
from nonebot.log import logger
from nonebot_plugin_larkcave.utils.decoder import decode_cave
from nonebot_plugin_larkcave.models import CaveData
from nonebot_plugin_larkcave.__main__ import cave
from nonebot_plugin_larkutils import get_user_id, is_user_superuser
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy.exc import NoResultFound
from nonebot_plugin_larkcave.lang import lang
from nonebot_plugin_larkcave.utils.comment.message import add_cave_message
from nonebot_plugin_larkcave.utils.comment.get import get_comments


@cave.assign("get.cave_id")
async def _(
    session: async_scoped_session, cave_id: int, user_id: str = get_user_id(), is_superuser: bool = is_user_superuser()
) -> None:
    try:
        cave_data = await session.get_one(CaveData, {"id": cave_id})
        content = await decode_cave(cave_data, session, user_id)
    except NoResultFound:
        await lang.finish("get.not_found", user_id, cave_id)
    if (not cave_data.public) and not is_superuser:
        await lang.finish("get.no_permission", user_id)
    if not ((cave_data.author == cave_data.author) or is_superuser):
        await lang.finish("get.no_permission", user_id)
    try:
        add_cave_message(cave_id, str((await content.send()).msg_ids[0]["message_id"]))
    except Exception:
        logger.error(f"写入回声洞消息队列时发生错误: {traceback.format_exc()}")
    if msg := await get_comments(cave_id, session, user_id):
        await msg.send()
    await cave.finish()
