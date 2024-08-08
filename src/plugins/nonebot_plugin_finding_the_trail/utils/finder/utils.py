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
import random
from typing import TypedDict

from ..fttmap import Directions, Blocks
from ..fttmap.directions import DIRECTION_LIST


def get_moved_pos(pos: list[int], direction: Directions) -> list[int]:
    match direction:
        case Directions.UP:
            return [pos[0]-1, pos[1]]
        case Directions.DOWN:
            return [pos[0]+1, pos[1]]
        case Directions.LEFT:
            return [pos[0], pos[1]-1]
        case Directions.RIGHT:
            return [pos[0], pos[1]+1]


def get_moveable_directions(
        pos: list[int],
        game_map: list[list[Blocks]],
        exclude_directions: list[Directions]
) -> list[Directions]:
    d_list = []
    for d in DIRECTION_LIST:
        p = get_moved_pos(pos, d)
        if game_map[p[0]][p[1]] not in [Blocks.WALL, Blocks.SAND] and d not in exclude_directions:
            d_list.append(d)
    random.shuffle(d_list)
    return d_list


class NodeData(TypedDict):
    game_map: list[list[Blocks]]
    pos: list[int]
    answer: list[Directions]


class MovementExecutor:

    def __init__(self, game_map: list[list[Blocks]], pos: list[int], direction: Directions) -> None:
        """
        执行移动
        :param game_map: 游戏地图
        :param pos: 当前座标
        :param direction: 移动方向
        """
        self.game_map = game_map
        self.pos = pos
        self.map_changed = False
        self.move(direction)
        self.remove_sand(pos)

    def get_moved_pos(self) -> list[int]:
        return self.pos

    def get_game_map(self) -> list[list[Blocks]]:
        return self.game_map

    def move(self, direction: Directions) -> None:
        while True:
            p = get_moved_pos(self.pos, direction)
            b = self.game_map[p[0]][p[1]]
            match b:
                case Blocks.NULL | Blocks.START:
                    self.pos = p
                case Blocks.PISTON:
                    self.pos = p
                    self.on_map_changing()
                    self.game_map[p[0]][p[1]] = Blocks.WALL
                case Blocks.SAND | Blocks.WALL:
                    break
                case Blocks.COBWEB | Blocks.END:
                    self.pos = p
                    break
                case Blocks.PORTAL:
                    self.pos = self.find_another_portal_pos(p)

    def find_another_portal_pos(self, pos: list[int]) -> list[int]:
        """
        寻找对应传送门座标
        :param pos: 其中一个座标
        :return: 另一个传送门座标
        """
        for row in range(len(self.game_map)):
            for col in range(len(self.game_map[row])):
                if self.game_map[row][col] == Blocks.PORTAL and [row, col] != pos:
                    return [row, col]

    def remove_sand(self, origin_pos: list[int]) -> None:
        """
        移除可被移除的沙子
        :param origin_pos: 移动前座标
        :return: 无返回
        """
        for d in DIRECTION_LIST:
            p = get_moved_pos(origin_pos, d)
            if self.game_map[p[0]][p[1]] == Blocks.SAND:
                self.on_map_changing()
                self.game_map[p[0]][p[1]] = Blocks.NULL

    def on_map_changing(self) -> None:
        if not self.is_map_changed():
            self.game_map = copy.deepcopy(self.game_map)

    def is_map_changed(self) -> bool:
        return self.map_changed


def get_back_direction(direction: Directions) -> Directions:
    match direction:
        case Directions.UP:
            return Directions.DOWN
        case Directions.DOWN:
            return Directions.UP
        case Directions.LEFT:
            return Directions.RIGHT
        case Directions.RIGHT:
            return Directions.LEFT
