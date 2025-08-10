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

from .monomer import Monomer
from abc import ABC

from .team import Team
import math


def monster_attack(lv: int) -> float:
    # 怪物输出曲线：前期稍弱于玩家，中后期渐强
    return (40 + 4.6 * lv) * math.log10(lv + 8)

def monster_hp(lv: int) -> float:
    # 怪物硬度曲线：前期接近玩家，越往后差距越大
    return (850 + 380 * math.log10(lv + 5)) * (1 + 0.0125 * lv)

class SimpleMonster(Monomer, ABC):

    def __init__(self, team: Team, level: int) -> None:
        self.level = level
        super().__init__(team)
        self.health = self.get_max_hp()
        self.attack = self.get_attack_value()

    def get_max_hp(self) -> int:
        return round(monster_hp(self.level))

    def get_attack_value(self) -> int:
        return round(monster_attack(self.level))






