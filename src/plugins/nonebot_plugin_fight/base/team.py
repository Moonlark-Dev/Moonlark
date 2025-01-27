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

from typing import TYPE_CHECKING
import copy
from ..lang import lang
from nonebot_plugin_fight.base.scheduler import Scheduler
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
        team_id: str = "team.a",
        selectable: bool = True,
        team_skill: None = None,
    ) -> None:
        self.team_id = team_id
        self.team_type = "Other"
        self.team_skill = team_skill
        self.max_skill_point = 5
        self.team_skill_power = 0
        self.selectable = selectable
        self.skill_point = 3
        self.monomers = []
        self.scheduler: "Scheduler" = scheduler.register_team(self)
        self.action_logs = []

    def get_skill_point(self) -> tuple[int, int]:
        self.skill_point = min(5, max(0, self.skill_point))
        return self.skill_point, 5

    async def get_team_name(self, user_id: str) -> str:
        return self.team_id

    def get_action_events(self) -> list[ACTION_EVENT]:
        events = copy.deepcopy(self.action_logs)
        self.action_logs.clear()
        return events

    async def got_event(self, event: ACTION_EVENT) -> None:
        if self.team_type == "Controllable":
            self.action_logs.append(event)
        for m in self.monomers:
            await m.on_event(event)

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


class ControllableTeam(Team):

    def __init__(
        self,
        scheduler: Scheduler,
        matcher: Matcher,
        user_id: str,
        team_id: str = "team.a",
        selectable: bool = True,
        team_skill: None = None,
    ) -> None:
        super().__init__(scheduler, team_id, selectable, team_skill)
        self.user_id = user_id
        self.matcher = matcher
        self.team_type = "Controllable"

    def get_user_id(self) -> str:
        return self.user_id

    async def parse_event(self, event: ACTION_EVENT) -> dict[str, Any]:
        if event["type"] == "harm.single":
            return {
                "type": "harm.single",
                "target_team": await event["target"].team.get_team_name(self.user_id),
                "target_name": await event["target"].get_name(self.user_id),
                "origin_team": await event["origin"].team.get_team_name(self.user_id),
                "origin_name": await event["origin"].get_name(self.user_id),
                "harm_value": event["harm_value"],
                "harm_type": await lang.text(f'harm_type._{event["harm_type"].value}', self.user_id),
                "harm_missed": event["harm_missed"],
            }
        return event  # type: ignore

    async def get_monomer_stat(self, monomer: "Monomer") -> str:
        if not monomer.is_selectable():
            k = "stat_unselectable"
        elif monomer.has_shield():
            k = "stat_with_shield"
        else:
            k = "stat"
        return await lang.text(
            k,
            self.user_id,
            round(monomer.get_hp() / monomer.get_max_hp()),
            monomer.balance,
            action_value=monomer.get_action_value(),
            shield=monomer.get_shield(),
        )
