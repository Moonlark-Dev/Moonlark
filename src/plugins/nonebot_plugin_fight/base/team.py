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

from typing import Awaitable, Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .monomer import Monomer


class Team:

    def __init__(self, team_id: str = "team.a", selectable: bool = True, team_skill: None = None) -> None:
        self.team_id = team_id
        self.team_skill = team_skill
        self.max_skill_point = 5
        self.team_skill_power = 0
        self.selectable = selectable
        self.skill_point = 3
        self.monomers = []

    def get_skill_points(self) -> int:
        return self.skill_point

    def reduce_skill_points(self, count: int = 1) -> int:
        self.skill_point -= count
        if self.skill_point <= 0:
            raise ValueError("没有可以减少的技能点")
        return self.skill_point

    def add_skill_points(self, count: int = 1) -> int:
        if self.reduce_skill_points(-count) >= self.max_skill_point:
            self.skill_point = self.max_skill_point
        return self.skill_point

    def has_skill_point(self, min_count: int = 1) -> int:
        return self.skill_point >= min_count

    def register_monomer(self, monomer: "Monomer") -> "Team":
        self.monomers.append(monomer)
        return self

    def is_selectable(self) -> bool:
        return self.selectable

    def get_team_id(self) -> str:
        return self.team_id

    def get_monomers(self) -> list["Monomer"]:
        return self.monomers
