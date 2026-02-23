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

from nonebot import on_command
from nonebot_plugin_orm import async_scoped_session


from nonebot_plugin_larkutils.user import get_user_id
from nonebot_plugin_userinfo import EventUserInfo, UserInfo

from ..utils.register import register_user
from ..lang import lang

register = on_command("register")


@register.handle()
async def _(
    session: async_scoped_session,
    # message: Message = CommandArg(),
    user: UserInfo = EventUserInfo(),
    user_id: str = get_user_id(),
) -> None:
    nickname = await register_user(session, user_id, user)
    await lang.finish("welcome", user_id, nickname or f"用户-{user_id}")

