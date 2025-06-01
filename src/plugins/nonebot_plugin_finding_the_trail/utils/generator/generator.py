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

# From https://github.com/Moonlark-Dev/XDbot2/blob/master/src/plugins/Core/lib/FindingTheTrail/map.py

from ..enums import Blocks
import random


def generate(
    row: int,
    column: int,
    blocks: list[tuple[Blocks, float]],
) -> list[list[Blocks]]:
    game_map = [[Blocks.NULL for _ in range(column)] for _ in range(row)]
    for r in range(row):
        for c in range(column):
            if r in [0, row - 1] or c in [0, column - 1]:
                game_map[r][c] = Blocks.WALL
                continue
            for block in blocks:
                if random.random() <= block[1]:
                    game_map[r][c] = block[0]
    while True:
        r = int(row / 2 + random.randint(1, row - 1) / 2)
        c = random.randint(1, column - 1)
        if game_map[r][c] == Blocks.NULL:
            game_map[r][c] = Blocks.START
            break
    return game_map
