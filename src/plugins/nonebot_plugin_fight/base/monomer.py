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

from abc import ABC, abstractmethod
import random
from typing import TYPE_CHECKING
from .team import Team
from ..types import ACTION_EVENT, AttackTypes, BuffData, BuffTypes


class Monomer(ABC):

    def __init__(self, team: Team):
        self.buff_list: list[BuffData] = []
        self.health = 100
        self.attack = 20
        self.critical_strike = (0.05, 1.50)
        self.speed = 97
        self.reduced_action_value = 0
        self.team = team.register_monomer(self)
        self.balance = 100
        self.final_skill_power = [0, 230]
        self.focus = 100
        self.defuse = 20
        self.shield = 0
        self.unset_speed = self.speed

    def get_shield(self) -> int:
        return self.shield

    def has_shield(self) -> bool:
        return self.shield > 0

    async def power_final_skill(self, value: int = 17) -> float:
        self.final_skill_power[0] += value
        if self.final_skill_power[0] >= self.final_skill_power[1]:
            self.final_skill_power[0] = self.final_skill_power[1]
        return self.final_skill_power[0] / self.final_skill_power[1]

    @abstractmethod
    def get_max_hp(self) -> int:
        return 100

    def get_hp(self) -> int:
        self.health = max(0, min(self.get_max_hp(), self.health))
        return self.health

    @abstractmethod
    async def get_name(self, user_id: str) -> str:
        return ""

    async def add_buff(self, buff: BuffData, force: bool = False) -> bool:
        self.buff_list.append(buff)
        return True

    async def setup(self, teams: list[Team]) -> None:
        pass

    def is_selectable(self) -> bool:
        return self.team.is_selectable()

    def reduce_action_value(self, value: float) -> None:
        self.reduced_action_value += value

    def reset_action_value(self) -> None:
        self.reduced_action_value = 0

    def get_action_value(self) -> float:
        return (100000 / self.speed) - self.reduced_action_value

    @abstractmethod
    async def on_action(self, teams: list[Team]) -> None:
        pass

    def clean_buff(self) -> None:
        removeable_index = []
        for i in range(len(self.buff_list)):
            if self.buff_list[i]["remain_rounds"] < 0:
                removeable_index.append(i)
        for index in removeable_index[::-1]:
            self.buff_list.pop(index)

    async def action(self, teams: list[Team]) -> None:
        for i in range(len(self.buff_list)):
            self.buff_list[i]["remain_rounds"] -= 1
        self.clean_buff()
        await self.on_action(teams)
        self.speed = self.unset_speed

    def get_power_percent(self) -> float:
        return min(self.final_skill_power[0] / self.final_skill_power[1], 1)

    def is_final_skill_powered(self) -> bool:
        return self.final_skill_power[0] >= self.final_skill_power[1]

    def reset_final_skill_power(self) -> None:
        self.final_skill_power[0] = 0

    async def is_actionable(self) -> bool:
        return self.get_hp() > 0 and self.balance > 0 and self.get_action_value() > 0

    def get_team(self) -> Team:
        return self.team

    def reduce_balance_value(self, value: int) -> int:
        self.balance -= value
        return self.balance

    def get_defuse(self) -> int:
        return round(self.defuse * (self.balance / 100))

    def break_shield(self, harm: int) -> int:
        if self.has_shield():
            self.shield -= harm
            harm = max(0, harm - self.shield)
            self.shield = max(0, self.shield)
        return harm

    async def attacked(self, type_: AttackTypes, harm: int, monomer: "Monomer", missed: bool) -> float:
        for buff in self.buff_list:
            if buff["buff_type"] == BuffTypes.lunar_eclipse_cracks and type_ == AttackTypes.ME:
                harm += round(harm * 0.15)
        if monomer in self.team.get_monomers():
            self.reduce_balance_value(15)
            return 0
        if type_ == AttackTypes.real:
            real_harm = harm
        else:
            real_harm = round(harm * (self.get_defuse() / monomer.get_defuse()))
        self.reduce_balance_value(int(real_harm / 2 * (monomer.get_attack_value() / self.get_attack_value())))
        self.health -= self.break_shield(real_harm)
        await self.team.scheduler.post_attack_event(self, monomer, real_harm, type_, True)
        return real_harm

    def get_attack_value(self) -> int:
        return self.attack

    async def on_event(self, event: ACTION_EVENT) -> None:
        pass

    async def on_attack(self, type_: AttackTypes, base_harm: float, target: "Monomer") -> tuple[float, bool, bool]:
        harm = base_harm
        missed = False
        critical = False
        if random.random() <= get_miss_percent(self, target):
            harm *= 0.4
            missed = True
        elif random.random() <= self.critical_strike[0]:
            harm *= self.critical_strike[1]
            critical = True
        return await target.attacked(type_, round(harm), self, missed), critical, missed

    def get_focus(self) -> int:
        return self.focus


def get_miss_percent(origin: Monomer, target: Monomer) -> float:
    "Calculate the miss percent that influenced by FOCUS value."
    return (origin.get_focus() - target.get_focus()) / 1000 + 0.05
