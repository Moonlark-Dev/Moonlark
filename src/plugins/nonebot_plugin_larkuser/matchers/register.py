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

from nonebot.adapters import Message
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot_plugin_orm import async_scoped_session

from nonebot_plugin_email.utils.send import send_email

from nonebot_plugin_larkutils.user import get_user_id
from nonebot_plugin_userinfo import EventUserInfo, UserInfo

from ..utils.register import register_user
from ..utils.base58 import base58_decode
from ..lang import lang
from ..user.utils import is_user_registered


register = on_command("register")


@register.handle()
async def _(
    session: async_scoped_session,
    message: Message = CommandArg(),
    user: UserInfo = EventUserInfo(),
    user_id: str = get_user_id(),
) -> None:
    invite_user = None
    if text := message.extract_plain_text():
        if await is_user_registered(user := base58_decode(text)):
            invite_user = user
        else:
            await lang.finish("invite.unknown", user_id)
    nickname = await register_user(session, user_id, user)
    await gain_invite(invite_user, user_id, user)
    await lang.finish("welcome", user_id, nickname or f"用户-{user_id}")


async def gain_invite(user_id: str, invited_user_id: str, invited_user_data: UserInfo) -> None:
    await send_email(
        [user_id],
        await lang.text("invite.inviter_email.subject", user_id),
        await lang.text("invite.inviter_email.content", user_id, invited_user_data.user_displayname or invited_user_id),
        items=[
            {"item_id": "special:vimcoin", "count": 200, "data": {}},
            {"item_id": "special:experience", "count": 10, "data": {}},
            {"item_id": "special:fav", "count": 1, "data": {}},
        ],
    )
    await send_email(
        [user_id],
        await lang.text("invite.invited_email.subject", invited_user_id),
        await lang.text("invite.invited_email.content", invited_user_id, user_id),
        items=[
            {"item_id": "special:vimcoin", "count": 30, "data": {}},
            {"item_id": "special:experience", "count": 5, "data": {}},
            {"item_id": "special:fav", "count": 7, "data": {"multiple": 1000}},  # 0.007
        ],
    )
