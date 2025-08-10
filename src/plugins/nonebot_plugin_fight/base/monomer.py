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
from .buff import Buff
from ..lang import lang
from ..types import ACTION_EVENT, AttackTypes, BuffTypes


class Monomer(ABC):

    def __init__(self, team: Team):
        self.buff_list: list[Buff] = []
        self.attack = 20
        self.critical_strike = (0.05, 1.50)
        self.speed = 97
        self.reduced_action_value = 0
        self.team = team.register_monomer(self)
        self.balance = 100
        self.final_skill_power = [0, 230]
        self.base_action_value = 100000
        self.focus = 100
        self.shield = 0
        self.defuse = 20
        self.health = self.get_max_hp()

    @abstractmethod
    def has_final_skill(self) -> bool: ...

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
        pass

    @abstractmethod
    def get_attack_type(self) -> AttackTypes: ...

    @abstractmethod
    def get_weakness_type(self) -> AttackTypes: ...

    def get_hp(self) -> int:
        self.health = max(0, min(self.get_max_hp(), self.health))
        return self.health

    async def get_self_stat(self, user_id: str) -> str:
        if self.get_hp() <= 0:
            return await lang.text("stat.monomer_stat_d", user_id, await self.get_name(user_id))

        return await lang.text(
            "stat.monomer_stat",
            user_id,
            await self.get_name(user_id),
            await lang.text(f"harm_type._{self.get_attack_type().value}", user_id),
            await lang.text(f"harm_type._{self.get_weakness_type().value}", user_id),
            await self.get_final_skill_string(user_id),
            f"{self.balance}%",
            (await lang.text("stat.hp.full", user_id)) * (f := round(12 * self.get_hp_percent()))
            + (await lang.text("stat.hp.line", user_id)) * (12 - f),
            buff=f"<br>{await self.get_buff_string(user_id)}",
        )

    async def get_final_skill_string(self, user_id: str) -> str:
        return "" if not self.has_final_skill() else await lang.text("stat.power", user_id, self.get_charge_percent())

    async def get_buff_string(self, user_id: str) -> str:
        l = []
        if self.balance <= 0:
            l.append(await lang.text("stat.lose_balance", user_id))
        return "<br>".join(l)

    def get_hp_percent(self) -> float:
        return min(1.0, self.get_hp() / self.get_max_hp())

    def get_charge_percent(self, readable: bool = True) -> float:
        if self.has_final_skill():
            percent = min(1.0, self.final_skill_power[0] / self.final_skill_power[1])
            return percent if not readable else round(percent * 100)
        return 0

    @abstractmethod
    async def get_name(self, user_id: str) -> str:
        return ""

    async def add_buff(self, buff: Buff, force: bool = False) -> bool:
        await buff.setup()
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
        return (self.base_action_value / self.speed) - self.reduced_action_value

    @abstractmethod
    async def on_action(self, teams: list[Team]) -> None:
        pass

    async def clean_buff(self) -> None:
        removable_index = []
        for i in range(len(self.buff_list)):
            if self.buff_list[i]["remain_rounds"] < 0:
                removable_index.append(i)
        for index in removable_index[::-1]:
            await self.buff_list.pop(index).remove()

    async def action(self, teams: list[Team]) -> None:
        for i in range(len(self.buff_list)):
            if self.buff_list[i]["remain_rounds"] != 114514:
                self.buff_list[i]["remain_rounds"] -= 1
        await self.clean_buff()
        self.add_balance_value(round(self.focus * 0.12))
        for i in range(len(self.buff_list)):
            await self.buff_list[i].action()
        if self.balance <= 0:
            self.balance = 100
        else:
            await self.on_action(teams)

    def get_power_percent(self) -> float:
        return min(self.final_skill_power[0] / self.final_skill_power[1], 1)

    def is_final_skill_powered(self) -> bool:
        return self.final_skill_power[0] >= self.final_skill_power[1]

    def reset_final_skill_power(self) -> None:
        self.final_skill_power[0] = 0

    async def is_actionable(self) -> bool:
        return self.get_hp() > 0

    def get_team(self) -> Team:
        return self.team

    def reduce_balance_value(self, value: int) -> int:
        self.balance -= value
        if self.balance <= 0 < self.balance + value:
            self.speed *= 0.9
            self.balance = round(self.balance + value - value * 0.2)
        return self.balance

    def add_balance_value(self, value: int) -> int:
        if self.balance < 100 <= self.balance + value:
            self.speed *= 1.1
        self.balance = min(100, self.balance + value)
        return self.balance

    def get_defuse(self) -> int:
        return round(self.defuse * ((self.balance - 50) / 100 + 1))

    def break_shield(self, harm: int) -> int:
        if self.has_shield():
            self.shield -= harm
            harm = max(0, harm - self.shield)
            self.shield = max(0, self.shield)
        return harm

    async def attacked(self, type_: AttackTypes, harm: int, monomer: "Monomer") -> float:
        if monomer in self.team.get_monomers():
            self.reduce_balance_value(15)
            return 0
        if type_ == AttackTypes.real or type_ == self.get_weakness_type():
            real_harm = harm
            self.reduce_balance_value(random.randint(25, 35))
        else:
            real_harm = round(harm * (self.get_defuse() / monomer.get_defuse()))
        self.reduce_balance_value(int(0.3 * (real_harm / 2) * (monomer.get_attack_value() / self.get_attack_value())))
        self.health -= self.break_shield(real_harm)
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
            await self.power_final_skill(10)
        else:
            await self.power_final_skill(5)
        await self.power_final_skill(5)
        removable_buff_index = []
        damage_increased_by_percent = 0.0
        for i in range(len(self.buff_list)):
            if self.buff_list[i].data["buff_type"] == BuffTypes.instant_damage_increased_by_percent:
                removable_buff_index.append(i)
                damage_increased_by_percent += self.buff_list[i].data["data"]["percent"]
            elif self.buff_list[i].data["buff_type"] == BuffTypes.damage_increased_by_percent:
                damage_increased_by_percent += self.buff_list[i].data["data"]["percent"]
        for i in removable_buff_index[::-1]:
            await self.buff_list[i].pop()
        print(f"{damage_increased_by_percent=} {harm=}")
        result = await target.attacked(type_, round(harm * (1 + damage_increased_by_percent)), self)
        await self.get_team().scheduler.post_attack_event(
            self, [{"target": target, "harm_missed": missed, "harm_value": round(result), "harm_type": type_}]
        )
        return result, critical, missed

    def get_focus(self) -> int:
        return self.focus


def get_miss_percent(origin: Monomer, target: Monomer) -> float:
    return (origin.get_focus() - target.get_focus()) / 1000 + 0.05
