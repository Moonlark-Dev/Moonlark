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
import random
from nonebot import logger
from ..base import Monomer, Team
from ..types import AttackTypes


class TestBot(Monomer):


    async def on_action(self, teams: list[Team]) -> None:
        r = await self.on_attack(AttackTypes.physical, 15, random.choice(teams[0].get_monomers()))
        logger.debug(f"{r=}")

    async def get_name(self, user_id: str) -> str:
        return "测试标靶"



    def get_weakness_type(self) -> AttackTypes:
        return AttackTypes.electricity



    def get_attack_type(self) -> AttackTypes:
        return AttackTypes.physical


    def get_max_hp(self) -> int:
        return 1000


    def has_final_skill(self) -> bool:
        return False

    def __init__(self, team: Team) -> None:
        super().__init__(team)

