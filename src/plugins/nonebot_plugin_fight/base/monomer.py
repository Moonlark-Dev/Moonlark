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
from .team import Team
from ..types import ACTION_EVENT, FinalSkillPowered


class Monomer(ABC):

    def __init__(self, team: Team):
        self.health = 100
        self.attack = 20
        self.critical_strike = (0.05, 1.50)
        self.speed = 97
        self.reduced_action_value = 0
        self.team = team.register_monomer(self)
        self.balance = 100
        self.final_skill_power = [0, 230]  # CURRENT, MAX | 目前考虑是不是只有 Controllable 有这个东西
        self.defuse = 20

    async def power_final_skill(self, value: int = 17) -> int:
        self.final_skill_power[0] += value
        if self.final_skill_power[0] >= self.final_skill_power[1]:
            event_data: FinalSkillPowered = {"type": "me.final_skill.powered"}
            await self.on_event(event_data)

    @abstractmethod
    def get_max_hp(self) -> int:
        return 100

    def get_hp(self) -> int:
        self.health = max(0, min(self.get_max_hp(), self.health))
        return self.health

    @abstractmethod
    async def get_name(self, user_id: str) -> str:
        return ""

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

    async def action(self, teams: list[Team]) -> None:
        await self.on_action(teams)

    def get_power_percent(self) -> float:
        return min(self.power_final_skill[0] / self.power_final_skill[1], 1)

    async def is_actionable(self) -> bool:
        return self.get_hp() > 0 and self.balance > 0

    def get_team(self) -> Team:
        return self.team

    def reduce_balance_value(self, value: int) -> int:
        self.balance -= value
        return self.balance

    def get_defuse(self) -> int:
        return round(self.defuse * (self.balance / 100))

    # TODO type_ 改为 Enum
    async def attacked(self, type_: str, harm: int, monomer: "Monomer") -> float:
        if monomer in self.team.get_monomers():
            self.reduce_balance_value(5)
            return 0
        real_harm = round(harm * (self.get_defuse() / monomer.get_defuse()))
        self.reduce_balance_value(int(real_harm / 2 * (monomer.get_attack_value() / self.get_attack_value())))
        self.health -= real_harm
        await self.team.scheduler.post_attack_event(self, monomer, real_harm, type_, False)
        return real_harm

    def get_attack_value(self) -> int:
        return self.attack

    async def on_event(self, event: ACTION_EVENT) -> None:
        pass

    async def on_attack(self, type_: str, base_harm: int, target: "Monomer") -> float:
        harm = base_harm
        if random.random() <= self.critical_strike[0]:
            harm *= self.critical_strike[1]
        return await target.attacked(type_, harm, self)
