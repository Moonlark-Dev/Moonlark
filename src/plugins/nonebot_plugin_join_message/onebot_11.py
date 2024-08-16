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

from nonebot.adapters.onebot.v11.event import GroupIncreaseNoticeEvent
from nonebot import on_type
from .lang import lang
from .data import on_group_joined


@ (matcher := on_type(GroupIncreaseNoticeEvent)).handle()
async def _(event: GroupIncreaseNoticeEvent) -> None:
    if event.self_id == event.group_id:
        await on_group_joined(str(event.self_id), str(event.group_id))
        await matcher.finish(await lang.text("join.message", "mlsid::--lang=default"))
