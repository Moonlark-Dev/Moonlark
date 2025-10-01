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

from nonebot.exception import ActionFailed
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_larkutils import get_user_id, get_group_id, is_public_qq_bot
from nonebot_plugin_schedule import complete_schedule
from nonebot import on_fullmatch

from ..__main__ import cave
from ..lang import lang
from ..utils.cave import send_cave
from ..utils.cool_down import is_user_cooled


async def handle_get_cave(
    session: async_scoped_session, user_id: str, group_id: str, reverse: bool = False, is_public_bot: bool = False
) -> None:
    if not (user_cd_data := await is_user_cooled(user_id, session, is_public_bot))[0]:
        await lang.finish("cave.user_cd", user_id, round(user_cd_data[1] / 60, 3))
    for _ in range(3):
        try:
            await send_cave(session, user_id, group_id, reverse)
        except ActionFailed:
            continue
        break
    else:
        await lang.finish("failed_to_send", user_id)
    await cave.finish()


@cave.assign("$main")
async def _(
    session: async_scoped_session,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
    is_public_bot: bool = is_public_qq_bot(),
) -> None:
    await complete_schedule(user_id, "cave")
    await handle_get_cave(session, user_id, group_id, False, is_public_bot)


@on_fullmatch("evac\\").handle()
async def _(session: async_scoped_session, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    await handle_get_cave(session, user_id, group_id, True)
