#  Moonlark - A new ChatBot
#  Copyright (C) 2024  Moonlark Development Team
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

from nonebot import on_command
from nonebot.adapters import Event
from nonebot_plugin_larkutils import get_user_id, get_group_id, is_user_superuser
from ..lang import lang
from ..utils.user import get_user


@on_command("whoami").handle()
async def _(
    event: Event, user_id: str = get_user_id(), group_id: str = get_group_id(), is_su: bool = is_user_superuser()
) -> None:
    user = await get_user(user_id)
    register_datetime = user.get_register_time()
    if register_datetime is not None:
        register_date = register_datetime.date().isoformat()
    else:
        register_date = None
    await lang.finish(
        "whoami.info", user_id, event.get_user_id(), user_id, user.get_nickname(), register_date, is_su, group_id
    )
