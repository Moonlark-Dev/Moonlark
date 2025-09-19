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

from typing import Optional
from nonebot_plugin_alconna import UniMessage

from nonebot_plugin_larkuser import get_user
from nonebot_plugin_render import render_template
from ...lang import lang
from ...models import CommentData
from nonebot_plugin_orm import AsyncSession, async_scoped_session
from sqlalchemy import select


async def get_comment_list(belong: int, session: async_scoped_session | AsyncSession) -> list[CommentData]:
    return list((await session.scalars(select(CommentData).where(CommentData.belong == belong))).all())


async def generate(comments: list[CommentData], cave_id: int, user_id: str) -> bytes:
    return await render_template(
        "cave_comment.html.jinja",
        await lang.text("comment.title", user_id, cave_id),
        user_id,
        {
            "comments": [
                {
                    "author": (await get_user(comment.author)).get_nickname(),
                    "time": comment.time.strftime("%Y-%m-%d %H:%M:%S"),
                    "id": await lang.text("comment.id", user_id, comment.id),
                    "text": comment.content.replace("<", "&lt;").replace(">", "&gt;"),
                }
                for comment in comments
            ]
        },
    )


async def get_comments(cave_id: int, session: async_scoped_session, user_id: str) -> Optional[UniMessage]:
    if not (comment_list := await get_comment_list(cave_id, session)):
        return None
    img = await generate(comment_list, cave_id, user_id)
    return UniMessage().image(raw=img)
