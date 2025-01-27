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


from nonebot_plugin_finding_the_trail.utils.enums.blocks import Blocks
from nonebot_plugin_finding_the_trail.utils.enums.directions import Directions
from .utils import (
    get_moveable_directions,
    MovementExecutor,
    get_back_direction,
)
from .finder import Finder


class EndFinder(Finder):

    def set_end_block(self) -> None:
        self.game_map[self.end_pos[0]][self.end_pos[1]] = Blocks.END

    def get_game_map(self) -> list[list[Blocks]]:
        return self.game_map

    def search(self) -> bool:
        stack = self.init_stack()
        while len(stack) > 0:
            node = stack.pop(0)
            executor = MovementExecutor(node["game_map"], node["pos"], node["answer"][-1])
            pos = executor.get_moved_pos()
            if pos[0] == 1 and len(node["answer"]) >= self.min_step:
                self.end_pos = [0, pos[1]]
                self.answer = node["answer"]
                if node["answer"][-1] != Directions.UP:
                    self.answer.append(Directions.UP)
                return True
            game_map = executor.get_game_map()
            if executor.is_map_changed():
                d_ignore = []
            else:
                d_ignore = [get_back_direction(node["answer"][-1])]
            if len(node["answer"]) >= self.step_limit:
                continue
            for d in get_moveable_directions(pos, game_map, d_ignore):
                stack.append({"game_map": game_map, "pos": pos, "answer": node["answer"] + [d]})
        return False

    def find_end(self) -> tuple[bool, list[list[Blocks]]]:
        result = self.search()
        if result:
            self.set_end_block()
        return result, self.game_map
