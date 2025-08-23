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
from ..base import Character, ControllableTeam, Monomer, Team
from ..buffs import StandardPercentGain, EmptyBuff, CriticalStrikeHarmGain, StandardGain
from ..types import CharacterData, AttackTypes, SkillInfo, BuffTypes

from enum import Enum


class MoonType(Enum):
    new = 0
    quarter = 1
    full = 2


class Moonlark(Character):

    def get_weakness_type(self) -> AttackTypes:
        return AttackTypes.null

    async def get_skill_info_list(self) -> list[SkillInfo]:
        return [
            {"name": "[普攻]", "monomer": self, "cost": -1, "charge": False, "instant": False, "target_type": "enemy"},
            {
                "name": "[战技]",
                "monomer": self,
                "cost": 1,
                "charge": False,
                "instant": False,
                "target_type": "none" if self.moon_type == MoonType.full else "enemy",
            },
            {
                "name": "[终结技]",
                "monomer": self,
                "cost": 0,
                "charge": True,
                "instant": True,
                "target_type": "enemy" if self.moon_type == MoonType.quarter else "none",
            },
        ]

    def get_attack_type(self) -> AttackTypes:
        return AttackTypes.sense

    def __init__(self, team: ControllableTeam, data: CharacterData) -> None:
        super().__init__(team, data)
        self.origin_hp = 902
        self.set_attack(76)
        self.final_skill_power[1] = 150
        self.moon_type = MoonType.new

    async def execute_skill(self, index: int, target: Optional[Monomer]) -> None:
        print(f"{self.moon_type.name=} {index=} {self.attack=}")
        if index == 0:
            await self.on_attack(AttackTypes.sense, self.get_attack_value() * 0.52, target)
        elif index == 1:
            if self.moon_type == MoonType.new:
                await self.on_attack(AttackTypes.sense, self.get_attack_value() * 0.80, target)
                await target.add_buff(
                    EmptyBuff({"buff_type": BuffTypes.moonlark_moon_seal, "remain_rounds": 114514, "data": {}}, target)
                )
            elif self.moon_type == MoonType.quarter:
                gain = 0
                buff_index_list = []
                for i in range(len(target.buff_list)):
                    if target.buff_list[i].data["buff_type"] == BuffTypes.moonlark_moon_seal:
                        gain += 10
                        buff_index_list.append(i)
                for index in buff_index_list[::-1]:
                    await target.buff_list[index].pop()
                await self.add_buff(
                    EmptyBuff(
                        {
                            "buff_type": BuffTypes.instant_damage_increased_by_percent,
                            "remain_rounds": 0,
                            "data": {"percent": gain / 100},
                        },
                        self,
                    )
                )
                await self.on_attack(AttackTypes.sense, self.get_attack_value() * 0.70, target)
            elif self.moon_type == MoonType.full:
                for monomer in self.team.scheduler.get_another_team(self.team).get_monomers():
                    await self.on_attack(AttackTypes.sense, self.get_attack_value(), monomer)
                    for _ in range(2):
                        await monomer.add_buff(
                            EmptyBuff(
                                {"buff_type": BuffTypes.moonlark_moon_seal, "remain_rounds": 114514, "data": {}},
                                monomer,
                            )
                        )
        elif index == 2:
            if self.moon_type == MoonType.new:
                await self.switch_moon_type(MoonType.full)
                for monomer in self.team.get_monomers():
                    await monomer.add_buff(
                        EmptyBuff(
                            {
                                "buff_type": BuffTypes.damage_increased_by_percent,
                                "remain_rounds": 1,
                                "data": {"percent": 0.20},
                            },
                            monomer,
                        )
                    )
                await self.on_action(self.team.scheduler.get_selectable_teams(self), False)
            elif self.moon_type == MoonType.quarter:
                gain = 0
                for i in range(len(target.buff_list)):
                    if target.buff_list[i].data["buff_type"] == BuffTypes.moonlark_moon_seal:
                        gain += 15
                await self.add_buff(
                    EmptyBuff(
                        {
                            "buff_type": BuffTypes.instant_damage_increased_by_percent,
                            "remain_rounds": 0,
                            "data": {"percent": gain / 100},
                        },
                        self,
                    )
                )
                await self.on_attack(AttackTypes.sense, self.get_attack_value() * 0.97, target)
            elif self.moon_type == MoonType.full:
                for monomer in self.team.scheduler.get_another_team(self.team).get_monomers():
                    await self.on_attack(AttackTypes.sense, self.get_attack_value() * 1.05, monomer)
                    for _ in range(4):
                        await monomer.add_buff(
                            EmptyBuff(
                                {"buff_type": BuffTypes.moonlark_moon_seal, "remain_rounds": 114514, "data": {}},
                                monomer,
                            )
                        )
                        await monomer.add_buff(
                            StandardPercentGain(
                                {
                                    "buff_type": BuffTypes.standard_debuff,
                                    "remain_rounds": 1,
                                    "data": {"attr": "base_action_value", "percent": 0.2},
                                },
                                monomer,
                            )
                        )

    async def on_action(self, teams: list[Team], change_moon_type: bool = True) -> None:
        await super().on_action(teams)
        if change_moon_type:
            await self.switch_moon_type(
                {MoonType.full: MoonType.new, MoonType.quarter: MoonType.full, MoonType.new: MoonType.quarter}[
                    self.moon_type
                ]
            )

    async def switch_moon_type(self, moon_type: MoonType) -> None:
        self.moon_type = moon_type
        if self.moon_type == MoonType.full:
            await self.add_buff(
                StandardPercentGain(
                    {
                        "buff_type": BuffTypes.standard_gain,
                        "remain_rounds": 1,
                        "data": {"attr": "attack", "percent": 1.2},
                    },
                    self,
                )
            )
            await self.add_buff(
                EmptyBuff(
                    {"buff_type": BuffTypes.damage_increased_by_percent, "remain_rounds": 1, "data": {"percent": 1.05}},
                    self,
                )
            )
        elif self.moon_type == MoonType.quarter:
            await self.add_buff(
                CriticalStrikeHarmGain(
                    {"buff_type": BuffTypes.standard_gain, "remain_rounds": 1, "data": {"value": 0.5}}, self
                )
            )
        else:
            await self.add_buff(
                StandardGain(
                    {"buff_type": BuffTypes.standard_gain, "remain_rounds": 1, "data": {"attr": "speed", "value": 1.5}},
                    self,
                )
            )

    async def get_extra_action_text(self) -> str:
        origin = super().get_extra_action_text()
        t = {0: "新月", 1: "弦月", 2: "满月"}
        return f"- 月相: {t[self.moon_type.value]}\n{origin}"

    @staticmethod
    def get_character_id() -> tuple[int, str]:
        return 2, "moonlark"
