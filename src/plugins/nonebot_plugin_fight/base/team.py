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

import stat
from typing import TYPE_CHECKING, Optional
import copy
from ..lang import lang
from ..base.scheduler import Scheduler
from ..types import ACTION_EVENT
from typing import Any
from nonebot.matcher import Matcher

if TYPE_CHECKING:
    from .monomer import Monomer
    from .scheduler import Scheduler


class Team:

    def __init__(
        self,
        scheduler: "Scheduler",
        team_id: str = "A",
        selectable: bool = True,
    ) -> None:
        self.team_id = team_id
        self.skill_point = [3, 5]
        self.selectable = selectable
        self.monomers: list["Monomer"] = []
        self.scheduler: "Scheduler" = scheduler.register_team(self)
        self.action_logs = []

    def get_skill_point(self) -> tuple[int, int]:
        self.skill_point[0] = min(5, max(0, self.skill_point[0]))
        return self.skill_point[0], self.skill_point[1]

    async def get_team_name(self, user_id: str) -> str:
        return self.team_id

    def get_action_events(self) -> list[ACTION_EVENT]:
        events = copy.deepcopy(self.action_logs)
        self.action_logs.clear()
        return events

    async def got_event(self, event: ACTION_EVENT) -> None:
        if isinstance(self, ControllableTeam):
            self.action_logs.append(event)
        for m in self.monomers:
            await m.on_event(event)

    def reduce_skill_points(self, count: int = 1) -> int:
        self.skill_point[0] -= count
        if self.skill_point[0] <= 0:
            raise ValueError("没有可以减少的技能点")
        return self.skill_point[0]

    def add_skill_points(self, count: int = 1) -> int:
        if self.reduce_skill_points(-count) >= self.skill_point[1]:
            self.skill_point[0] = self.skill_point[1]
        return self.skill_point[0]

    def has_skill_point(self, min_count: int = 1) -> int:
        return self.skill_point[0] >= min_count

    def register_monomer(self, monomer: "Monomer") -> "Team":
        self.monomers.append(monomer)
        return self

    def is_selectable(self) -> bool:
        return self.selectable

    def get_team_id(self) -> str:
        return self.team_id

    def get_monomers(self) -> list["Monomer"]:
        return self.monomers
    
    async def get_monomer_stat_list(self, user_id: str) -> list[str]:
        return [stat for monomer in self.monomers for stat in await monomer.get_self_stat(user_id)]


class ControllableTeam(Team):

    def __init__(
        self,
        scheduler: Scheduler,
        matcher: Matcher,
        user_id: str,
        team_id: str = "A",
        selectable: bool = True,
        team_skill: None = None,
    ) -> None:
        super().__init__(scheduler, team_id, selectable, team_skill)
        self.user_id = user_id
        self.matcher = matcher

    def get_user_id(self) -> str:
        return self.user_id