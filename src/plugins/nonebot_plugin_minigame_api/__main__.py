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

from pathlib import Path
import aiofiles
import json
from nonebot_plugin_alconna import Alconna, on_alconna, Subcommand, Args, Match, UniMessage
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_ranking import generate_image
from nonebot_plugin_render import render_template
from .ranking import get_rank_user

matcher = on_alconna(Alconna("minigame-rank"))
lang = LangHelper()



@matcher.assign("$main")
async def _(user_id: str = get_user_id()) -> None:
    image = await generate_image(
        sorted([u async for u in get_rank_user(user_id)], key=lambda x: x["data"], reverse=True),
        user_id,
        await lang.text("command.ranking_title", user_id),
    )
    await matcher.finish(UniMessage().image(raw=image))
