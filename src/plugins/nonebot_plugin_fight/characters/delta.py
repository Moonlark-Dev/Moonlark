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
from typing import Optional
import random
from ..base import Character, ControllableTeam, Monomer
from ..types import CharacterData, AttackTypes, SkillInfo


class Delta(Character):

    def get_weakness_type(self) -> AttackTypes:
        return AttackTypes.sense

    async def get_skill_info_list(self) -> list[SkillInfo]:
        return [
            {"name": "[普攻]", "monomer": self, "cost": -1, "charge": False, "instant": False, "target_type": "enemy"},
            {"name": "[战技]", "monomer": self, "cost": 1, "charge": False, "instant": False, "target_type": "enemy"},
            {"name": "[终结技]", "monomer": self, "cost": 0, "charge": True, "instant": True, "target_type": "none"},
        ]

    def get_attack_type(self) -> AttackTypes:
        return AttackTypes.electricity

    def __init__(self, team: ControllableTeam, data: CharacterData) -> None:
        super().__init__(team, data)
        self.origin_hp = 902
        self.set_attack(76)
        self.final_skill_power[1] = 150

    async def execute_skill(self, index: int, target: Optional[Monomer]) -> None:
        print(f"{index=}")
        if index == 0:
            await self.on_attack(AttackTypes.electricity, self.get_attack_value() * 0.8, target)
        elif index == 1:
            harm, critical, missed = await self.on_attack(AttackTypes.electricity, self.get_attack_value(), target)
            if not missed:
                p = 0.5 if critical else 0.3
                self.focus -= 20
                m = target.team.get_monomers()
                index = m.index(target)
                if index > 0:
                    await self.on_attack(AttackTypes.electricity, harm * p, m[index - 1])
                if index < len(m) - 1:
                    await self.on_attack(AttackTypes.electricity, harm * p, m[index + 1])
                self.focus += 20
        elif index == 2:
            monomers = self.team.scheduler.get_another_team(self.get_team()).get_monomers()
            for _ in range(5):
                await self.on_attack(AttackTypes.electricity, self.get_attack_value() * 0.5, random.choice(monomers))
                self.focus -= 5
            self.focus += 25

    @staticmethod
    def get_character_id() -> tuple[int, str]:
        return 1, "delta"
