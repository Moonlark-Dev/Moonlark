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
from nonebot_plugin_waiter import prompt_until

from .map2048 import Map2048
from ....nonebot_plugin_finding_the_trail.exceptions import Quited
from ....nonebot_plugin_larklang import LangHelper
from ....nonebot_plugin_larkutils import get_user_id
from ....nonebot_plugin_larkuser import patch_matcher
from ....nonebot_plugin_finding_the_trail.utils.enums.directions import Directions
from ..nonebot_plugin_minigames_api import create_minigame_session
from nonebot_plugin_alconna import UniMessage

lang = LangHelper()
cmd = on_command("2048")
patch_matcher(cmd)


async def get_input(game_map: Map2048, user_id: str) -> Directions:
    while True:
        message = await prompt_until(
            await UniMessage().image(raw=game_map.draw()).text(
                await lang.text("game.prompt", user_id, game_map.get_score())
            ).export(),
            lambda msg: msg.extract_plain_text().lower() in ["w", "s", "a", "d", "q"],
            retry_prompt=await lang.text("game.input", user_id)
        )
        if message is None:
            continue
        text = message.extract_plain_text().lower()
        if text == "q":
            raise Quited
        return {
            "w": Directions.UP,
            "s": Directions.DOWN,
            "a": Directions.LEFT,
            "d": Directions.RIGHT
        }[text]


@cmd.handle()
async def _(user_id: str = get_user_id()) -> None:
    session = await create_minigame_session(user_id)
    game_map = Map2048()
    while True:
        try:
            game_map.put_number()
        except ValueError:
            break
        try:
            direction = await get_input(game_map, user_id)
        except Quited:
            break
        if not game_map.move(direction):
            await lang.text("game.cannot_move", user_id)
    t = await session.finish()
    p = await session.add_points(round(game_map.get_score() * 0.8))
    await lang.finish("game.failed", user_id, round(t, 1), p, game_map.get_score())

