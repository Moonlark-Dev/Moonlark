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

import os
import struct
from nonebot_plugin_schedule.utils import complete_schedule
from nonebot_plugin_waiter import prompt
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_minigame_api import create_minigame_session
from .exceptions import Quited, CannotMove
from .utils.fttmap import FttMap
from .utils.enums import Directions
from .utils.string import get_command_list_string
from .utils.answer import AnswerGetter
from .__main__ import ftt, lang


async def is_user_continue(user_id: str, d_list: list[Directions]) -> bool:
    while True:
        inp = await prompt(await lang.text("ftt.done", user_id, await get_command_list_string(d_list, user_id)))
        if inp is None:
            continue
        text = inp.extract_plain_text().lower()
        if text == "ok":
            return True
        elif text == "clear":
            return False


@ftt.handle()
async def _(seed: str, user_id: str = get_user_id()) -> None:
    map_seed = seed if seed != "-1" else str(struct.unpack("I", os.urandom(4))[0])
    ftt_map = FttMap(map_seed)
    points = ftt_map.difficulty["points"]
    session = await create_minigame_session(user_id, "ftt")
    while points >= 2:
        getter = AnswerGetter(user_id, ftt_map)
        try:
            d_list = await getter.get_commands()
        except Quited:
            await session.quit(await lang.text("ftt.example", user_id, await get_command_list_string(ftt_map.answer, user_id), map_seed))
        if not await is_user_continue(user_id, d_list):
            continue
        try:
            result = ftt_map.test_answer(d_list)
        except CannotMove as e:
            if points / 2 >= 2:
                points /= 2
                await lang.send("ftt.cannot_move", user_id, e.step_length + 1)
                continue
            else:
                await lang.send("ftt.cannot_move_end", user_id, e.step_length + 1)
                break
        if points / 2 >= 2 and not result:
            points /= 2
            await lang.send("ftt.failed", user_id)
        elif not result:
            await lang.send("ftt.big_failed", user_id)
            break
        else:
            if seed != "-1":
                points = 5
            t, points = await session.finish(round(points * (ftt_map.step_length / 5)), 1.6)
            if ftt_map.difficulty_name != "easy":
                await complete_schedule(user_id, "ftt")
            await lang.finish("ftt.success", user_id, points, map_seed)
    await session.quit(
        await lang.text("ftt.example", user_id, await get_command_list_string(ftt_map.answer, user_id), map_seed)
    )
