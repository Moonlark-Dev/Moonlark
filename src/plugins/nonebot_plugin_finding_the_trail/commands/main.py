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

import random
import time
from nonebot_plugin_waiter import prompt
from nonebot_plugin_alconna import Match
from ...nonebot_plugin_larkutils import get_user_id
from ..exceptions import Quited, CannotMove
from ..utils.fttmap import FttMap
from ..utils.enums import Directions
from ..utils.string import get_command_list_string
from ..utils.answer import AnswerGetter
from ..__main__ import ftt, lang
from ..utils.points import add_point


async def is_user_continue(user_id: str, d_list: list[Directions]) -> bool:
    while True:
        inp = await prompt(await lang.text("ftt.done", user_id, await get_command_list_string(d_list, user_id)))
        text = inp.extract_plain_text().lower()
        if text == "ok":
            return True
        elif text == "clear":
            return False


@ftt.assign("$main")
@ftt.assign("seed")
async def _(seed: Match[str], user_id: str = get_user_id()) -> None:
    if seed.available:
        map_seed = seed.result
    else:
        map_seed = random.randint(0, 2**32 - 1)
    ftt_map = FttMap(map_seed)
    points = ftt_map.difficulty["points"]
    start_time = time.time()
    while points >= 2:
        getter = AnswerGetter(user_id, ftt_map)
        try:
            d_list = await getter.get_commands()
        except Quited:
            await lang.send("ftt.quited", user_id)
            break
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
            points *= 10 / (time.time() - start_time)
            points = round(points)
            if seed.available:
                points = 0
            await add_point(user_id, points)
            await lang.finish("ftt.success", user_id, points)
    # TODO 参考答案动画
    # TODO 错误答案演示
    await lang.finish("ftt.example", user_id, await get_command_list_string(
        ftt_map.answer, user_id))


