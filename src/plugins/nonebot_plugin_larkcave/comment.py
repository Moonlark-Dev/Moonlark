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
from nonebot import on_message
from nonebot.rule import to_me

from nonebot.params import Depends
from nonebot_plugin_larkcave.lang import lang
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_larkutils import get_user_id, review_text
from nonebot_plugin_larkcave.utils.comment.post import get_belong_cave, get_message, post

comment = on_message(rule=to_me(), block=False)


@comment.handle()
async def _(
    session: async_scoped_session,
    content: str = Depends(get_message),
    user_id: str = get_user_id(),
    cave_id: Optional[int] = Depends(get_belong_cave),
) -> None:
    if cave_id is None or not content:
        await comment.finish()
    if not (result := await review_text(content))["compliance"]:
        await lang.finish("comment.review_fail", user_id, result["message"])
    await lang.finish("comment.success", user_id, await post(user_id, session, content, cave_id))



