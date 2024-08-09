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

from src.plugins.nonebot_plugin_finding_the_trail.utils.enums.blocks import Blocks

DIFFICULTIES = {
    "easy": {
        "map": {
            "row": 6,
            "column": 8,
            "blocks": [(Blocks.WALL, 2 / 15), (Blocks.PISTON, 1 / 15)],
            "portal": False,
        },
        "finder": {
            "step_limit": 12,
            "min_step": 4,
        },
        "points": 10
    },
    "normal": {
        "map": {
            "row": 9,
            "column": 12,
            "blocks": [(Blocks.WALL, 0.1), (Blocks.PISTON, 0.1), (Blocks.SAND, 0.1), (Blocks.COBWEB, 0.1)],
            "portal": False,
        },
        "finder": {
            "step_limit": 17,
            "min_step": 5,
        },
        "points": 25
    },
    "hard": {
        "map": {
            "row": 18,
            "column": 24,
            "blocks": [(Blocks.PISTON, 0.1), (Blocks.SAND, 0.1), (Blocks.COBWEB, 0.1), (Blocks.WALL, 0.2)],
            "portal": True,
        },
        "finder": {
            "step_limit": 20,
            "min_step": 7,
        },
        "points": 100
    },
}
