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

import copy

from nonebot_plugin_finding_the_trail.utils.enums.blocks import Blocks
from nonebot_plugin_finding_the_trail.utils.enums.directions import Directions
from .utils import (
    get_moveable_directions,
    MovementExecutor,
    get_back_direction,
)
from .finder import Finder


class AnswerFinder(Finder):

    def search(self) -> list[Directions]:
        stack = self.init_stack()
        while len(stack) > 0:
            node = stack.pop(0)
            executor = MovementExecutor(node["game_map"], node["pos"], node["answer"][-1])
            pos = executor.get_moved_pos()
            game_map = executor.get_game_map()
            if game_map[pos[0]][pos[1]] == Blocks.END:
                self.answer = node["answer"]
                return self.answer
            if executor.is_map_changed():
                d_ignore = []
            else:
                d_ignore = [get_back_direction(node["answer"][-1])]
            for d in get_moveable_directions(pos, game_map, d_ignore):
                stack.append({"game_map": game_map, "pos": pos, "answer": node["answer"] + [d]})
        return []
