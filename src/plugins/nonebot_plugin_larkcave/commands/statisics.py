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

from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_orm import async_scoped_session

from nonebot_plugin_larkcave.__main__ import cave
from nonebot_plugin_larkcave.lang import lang
from nonebot_plugin_larkcave.utils.statisics import (
    merge_small_poster,
    set_nickname_for_posters,
    get_poster_data,
    render_pie,
)
from nonebot_plugin_larkutils import get_user_id


@cave.assign("statisics")
async def _(session: async_scoped_session, user_id: str = get_user_id()) -> None:
    await lang.send("stat.tip", user_id)
    d = await merge_small_poster(await set_nickname_for_posters(await get_poster_data(session), user_id), user_id)
    img = await render_pie(d, user_id)
    await cave.finish(UniMessage().image(raw=img))
