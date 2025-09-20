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

from typing import cast
from nonebot_plugin_alconna import Arparma, Image, Text
from nonebot.adapters import Event
from nonebot.adapters import Bot
from nonebot.typing import T_State
from nonebot_plugin_orm import async_scoped_session

from nonebot_plugin_larkcave.__main__ import cave
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larkcave.lang import lang
from nonebot_plugin_larkcave.utils.post import post_cave


@cave.assign("add.content")
async def _(
    session: async_scoped_session, event: Event, bot: Bot, state: T_State, result: Arparma, user_id: str = get_user_id()
) -> None:
    try:
        content = cast(list[Image | Text], list(result.subcommands["add"].args["content"]))
    except KeyError:
        await lang.finish("add.empty", user_id)
        return
    await post_cave(content, user_id, event, bot, state, session)
