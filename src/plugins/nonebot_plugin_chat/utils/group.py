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

from nonebot.adapters import Bot
from nonebot.adapters import Event
from nonebot.typing import T_State
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_orm import get_session
from nonebot_plugin_larkutils import get_group_id, get_user_id

from nonebot.adapters.onebot.v11 import Bot as OneBotV11Bot

from ..models import ChatGroup


async def group_message(event: Event) -> bool:
    return event.get_user_id() != event.get_session_id()


async def enabled_group(event: Event, group_id: str = get_group_id(), user_id: str = get_user_id()) -> bool:
    async with get_session() as session:
        return bool(
            (await group_message(event)) and (g := await session.get(ChatGroup, {"group_id": group_id})) and g.enabled
        )

from .message import parse_message_to_string as _parse_message_to_string

async def parse_message_to_string(message: UniMessage, event: Event, bot: Bot, state: T_State) -> str:
    return await _parse_message_to_string(message, event, bot, state)