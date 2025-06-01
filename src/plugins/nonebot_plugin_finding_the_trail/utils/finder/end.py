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
from nonebot.log import logger
from typing import Optional

from nonebot_plugin_finding_the_trail.utils.enums.blocks import Blocks
from nonebot_plugin_finding_the_trail.utils.enums.directions import Directions
from .utils import (
    get_moveable_directions,
    MovementExecutor,
    get_back_direction,
)
from .finder import Finder


def get_portal_pos(game_map: list[list[Blocks]]) -> Optional[tuple[tuple[int, int], tuple[int, int]]]:
    p = []
    for row in range(len(game_map)):
        for col in range(len(game_map[row])):
            if game_map[row][col] == Blocks.PORTAL:
                p.append((row, col))
    if p:
        return p[0], p[1]
    return None


class EndFinder(Finder):

    def __init__(self, game_map: list[list[Blocks]], step_limit: int = -1, min_step: int = 0, portal: bool = False) -> None:
        super().__init__(game_map, step_limit, min_step, portal)

    def set_end_block(self) -> None:
        self.game_map[self.end_pos[0]][self.end_pos[1]] = Blocks.END

    def get_game_map(self) -> list[list[Blocks]]:
        return self.game_map

    def search(self) -> Optional[tuple[tuple[int, int], tuple[int, int]]]:
        stack = self.init_stack()
        portal_placed = not self.portal
        max_step = (0, 0, None)
        while len(stack) > 0:
            node = stack.pop(0)
            executor = MovementExecutor(node["game_map"], node["pos"], node["answer"][-1])
            pos = executor.get_moved_pos()
            if pos[0] == 1:
                if step := len(node["answer"]) >= self.min_step:
                    self.end_pos = [0, pos[1]]
                    self.answer = node["answer"]
                    if node["answer"][-1] != Directions.UP:
                        self.answer.append(Directions.UP)
                    return get_portal_pos(executor.get_game_map())
                elif step >= max_step[0]:
                    max_step = step, pos[1], get_portal_pos(executor.get_game_map())
                continue
            game_map = executor.get_game_map()
            if (not portal_placed) and game_map[pos[0]][pos[1]] == Blocks.NULL and random.random() <= 0.75:
                executor.on_map_changing()
                game_map = executor.get_game_map()
                game_map[pos[0]][pos[1]] = Blocks.PORTAL
                game_map, pos = self.place_portal(game_map)
                portal_placed = True
                stack.insert(0, {"game_map": game_map, "pos": [pos[0], pos[1]], "answer": node["answer"]})
                continue
            if executor.is_map_changed():
                d_ignore = []
            else:
                d_ignore = [get_back_direction(node["answer"][-1])]
            if len(node["answer"]) >= self.step_limit:
                continue
            for d in get_moveable_directions(pos, game_map, d_ignore):
                stack.append({"game_map": game_map, "pos": pos, "answer": node["answer"] + [d]})
        self.end_pos = [0, max_step[1]]
        return max_step[2]

    def place_portal(self, game_map: list[list[Blocks]]) -> tuple[list[list[Blocks]], tuple[int, int]]:
        while True:
            pos = random.randint(1, len(game_map) - 2), random.randint(1, len(game_map) - 2)
            if self.game_map[pos[0]][pos[1]] == Blocks.NULL and game_map[pos[0]][pos[1]] == Blocks.NULL:
                game_map[pos[0]][pos[1]] = Blocks.PORTAL
                return game_map, pos

    def find_end(self) -> tuple[bool, list[list[Blocks]]]:
        portal_pos = self.search()
        self.set_end_block()
        if portal_pos:
            self.set_portal(portal_pos)
        logger.debug(portal_pos)
        return True, self.game_map

    def set_portal(self, portal_pos: tuple[tuple[int, int], tuple[int, int]]) -> None:
        for p in portal_pos:
            self.game_map[p[0]][p[1]] = Blocks.PORTAL
