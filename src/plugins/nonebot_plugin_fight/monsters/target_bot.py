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

from ..base import SimpleMonster, Team
from ..lang import lang
from ..types import AttackTypes


class TargetBot(SimpleMonster):

    def get_weakness_type(self) -> AttackTypes:
        return AttackTypes.physical

    def get_attack_type(self) -> AttackTypes:
        return AttackTypes.physical

    async def get_name(self, user_id: str) -> str:
        return lang.text("monsters.target_bot", user_id)

    def has_final_skill(self) -> bool:
        return False

    async def on_action(self, teams: list[Team]) -> None:
        target = random.choice(teams[0].get_monomers())
        await self.on_attack(self.get_attack_type(), self.get_attack_value(), target)
