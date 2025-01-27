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

from nonebot_plugin_alconna import on_alconna, Alconna, UniMessage
from nonebot_plugin_minigame_api import create_minigame_session
from nonebot_plugin_larkuser.utils.waiter import prompt
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_htmlrender import md_to_pic
from .data_source import get_question

matcher = on_alconna(Alconna("manual-copy"))
lang = LangHelper()


@matcher.handle()
async def _(user_id: str = get_user_id()) -> None:
    question = await get_question()
    raw_image = await md_to_pic(await lang.text("question", user_id, question["text"], question["origin"]))
    image = UniMessage().image(raw=raw_image)
    session = await create_minigame_session(user_id)
    await prompt(image, user_id, lambda string: string.strip() == question["text"])
    t = await session.finish()
    points = await session.add_points(round(question["length"] / t * 100))
    await lang.finish("finish", user_id, round(t, 3), points)
