#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
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

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import Alconna, Args, At, Match, on_alconna
from nonebot_plugin_larkutils import get_main_account, get_user_id

from ..lang import lang
from ..utils.matcher import patch_matcher
from ..utils.nickname import get_nickname

getid = patch_matcher(on_alconna(Alconna("id", Args["target?", At])))


@getid.handle()
async def _(
    bot: Bot,
    event: Event,
    target: Match[At],
    user_id: str = get_user_id(),
) -> None:
    target_id = target.result.target if target.available else user_id
    main_account_id = await get_main_account(target_id)
    nickname = await get_nickname(target_id, bot, event)
    await lang.finish(
        "getid.info",
        user_id,
        nickname,
        target_id,
        main_account_id,
    )
