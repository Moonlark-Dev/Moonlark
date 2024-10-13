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
from abc import ABC
from src.plugins.nonebot_plugin_finding_the_trail.utils.enums import Blocks
from .utils import NodeData, get_moveable_directions


class Finder(ABC):

    def __init__(self, game_map: list[list[Blocks]], step_limit: int = -1, min_step: int = 0) -> None:
        self.step_limit = step_limit
        self.min_step = min_step
        self.game_map = game_map
        self.end_pos = [0, 0]
        self.answer = []

    def get_start_pos(self) -> list[int]:
        for row in range(len(self.game_map)):
            for col in range(len(self.game_map[row])):
                if self.game_map[row][col] == Blocks.START:
                    return [row, col]
        raise ValueError("No start block found")

    def init_stack(self) -> list[NodeData]:
        start_pos = self.get_start_pos()
        return [
            {"game_map": copy.deepcopy(self.game_map), "pos": start_pos, "answer": [d]}
            for d in get_moveable_directions(start_pos, self.game_map, [])
        ]
