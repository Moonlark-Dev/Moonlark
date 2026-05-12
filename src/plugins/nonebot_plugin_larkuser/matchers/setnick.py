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

import json

from nonebot import on_command
from nonebot.adapters import Message
from nonebot.params import CommandArg
from nonebot_plugin_orm import get_session

from nonebot_plugin_larkutils import get_user_id, review_text

from ..utils.matcher import patch_matcher
from ..utils.user import get_user
from ..models import UserData
from ..lang import lang

setnick = patch_matcher(on_command("setnick"))


@setnick.handle()
async def _(
    args: Message = CommandArg(),
    user_id: str = get_user_id(),
) -> None:
    new_nick = args.extract_plain_text().strip()

    if not new_nick:
        await lang.finish("setnick.usage", user_id)

    if len(new_nick) > 27:
        await lang.finish("setnick.too_long", user_id)

    current_user = await get_user(user_id)
    current_nick = current_user.get_nickname()

    if new_nick == current_nick:
        await lang.finish("setnick.same", user_id)

    review_result = await review_text(new_nick)
    if not review_result["conclusion"]:
        await lang.finish("setnick.review_failed", user_id, review_result["message"])

    async with get_session() as session:
        user = await session.get(UserData, user_id)
        if user is None:
            await lang.finish("setnick.failed", user_id)
            return
        user.nickname = new_nick
        config = json.loads(user.config)
        config["lock_nickname"] = True
        user.config = json.dumps(config)
        await session.commit()

    await lang.finish("setnick.success", user_id, new_nick)
