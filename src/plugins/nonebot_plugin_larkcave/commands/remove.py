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

from nonebot_plugin_larkcave.__main__ import cave
from nonebot_plugin_larkutils import get_user_id, is_user_superuser
from nonebot_plugin_larkcave.lang import lang
from nonebot_plugin_larkcave.models import CaveData, RemovedCave, CommentData
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkcave.config import config
from sqlalchemy.exc import NoResultFound
from datetime import datetime, timedelta
from nonebot_plugin_larkcave.utils.decoder import decode_cave


@cave.assign("remove.comment.comment_id")
async def _(
    comment_id: int,
    session: async_scoped_session,
    is_superuser: bool = is_user_superuser(),
    user_id: str = get_user_id(),
) -> None:
    try:
        comment = await session.get_one(CommentData, {"id": comment_id})
    except NoResultFound:
        await lang.finish("remove_comment.no_result", user_id, comment_id)
        return
    if not (comment.author == user_id or is_superuser):
        await lang.reply()
        await cave.finish()
    await lang.send(
        "remove_comment.info",
        user_id,
        (await get_user(comment.author)).nickname,
        comment.belong,
        comment.content,
        at_sender=False,
    )
    await session.delete(comment)
    await session.commit()
    await lang.finish("remove_comment.success", user_id, comment_id)


@cave.assign("remove.cave_id")
async def _(
    cave_id: int, session: async_scoped_session, is_superuser: bool = is_user_superuser(), user_id: str = get_user_id()
) -> None:
    try:
        cave_data = await session.get_one(CaveData, {"id": cave_id})
    except NoResultFound:
        await lang.reply()
        await cave.finish()
    if not (cave_data.author == user_id or is_superuser):
        await lang.reply()
        await cave.finish()
    if not cave_data.public:
        await lang.reply()
        await cave.finish()
    cave_data.public = False
    session.add(
        RemovedCave(
            id=cave_data.id,
            expiration_time=datetime.now() + timedelta(days=config.cave_restore_date),
            superuser=is_superuser,
        )
    )
    post_time = cave_data.time.strftime("%Y-%m-%dT%H:%M:%S")
    await (await decode_cave(cave_data, session, user_id)).send()
    await session.commit()
    await lang.finish("remove.success", user_id, cave_id, post_time, config.cave_restore_date, cave_id)
