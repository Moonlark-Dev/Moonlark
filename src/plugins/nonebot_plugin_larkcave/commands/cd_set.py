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

from nonebot_plugin_alconna import AlconnaMatch, Arparma, Match
from nonebot_plugin_larkcave.__main__ import cave
from nonebot_plugin_larkcave.lang import lang
from nonebot_plugin_larkutils import get_user_id, get_group_id
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_larkcave.utils.cool_down import is_group_cooled, is_user_cooled, set_cool_down


@cave.assign("cd")
async def _(
    session: async_scoped_session,
    alc_result: Arparma,
    time: Match[float] = AlconnaMatch("time"),
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
    is_superuser: bool = get_user_id(),
) -> None:
    if time.available:
        if is_superuser:
            await set_cool_down(group_id, time.result, session)
            await lang.finish("cd.set", user_id)
        else:
            await lang.finish("cd.no_permission", user_id)
    if alc_result.find("cd.user"):
        result = await is_user_cooled(user_id, session)
        await lang.finish(
            "cd.info_user",
            user_id,
            await lang.text("cd.info_status_ok" if result[0] else "cd.info_status_cooling", user_id),
            0 if result[0] else round(result[1] / 60, 3),
            at_sender=False,
        )
    result = await is_group_cooled(group_id, session)
    await lang.finish(
        "cd.info",
        user_id,
        await lang.text("cd.info_status_ok" if result[0] else "cd.info_status_cooling", user_id),
        0 if result[0] else round(result[1] / 60, 3),
        at_sender=False,
    )
