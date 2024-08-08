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

from .difficulties import DIFFICULTIES
from ..generator.generator import generate
from .blocks import Blocks
from ..finder import EndFinder, AnswerFinder
from .directions import Directions


class FttMap:

    def __init__(self, seed: str) -> None:
        random.seed(seed)
        self.difficulty = DIFFICULTIES[random.choice(list(DIFFICULTIES.keys()))]
        self.map, self.answer, self.start_pos = self.generate_map()
        self.step_length = len(self.answer)

    def generate_map(self) -> tuple[list[list[Blocks]], list[Directions], list[int]]:
        game_map = generate(**self.difficulty["map"])
        end_finder = EndFinder(game_map, **self.difficulty["finder"])
        result, game_map = end_finder.find_end()
        if not result:
            raise ValueError("生成地图时出现错误！")
        answer = AnswerFinder(copy.deepcopy(game_map)).search()
        return game_map, answer, end_finder.get_start_pos()
