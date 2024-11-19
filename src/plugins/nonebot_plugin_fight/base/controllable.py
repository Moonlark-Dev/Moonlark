import copy

from ..types import ACTION_EVENT  #  Moonlark - A new ChatBot

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

from ...nonebot_plugin_larkuser.utils.waiter2 import WaitUserInput
from .monomer import Monomer, Team, ACTION_EVENT
from ..lang import lang
from abc import ABC
from ...nonebot_plugin_render import render_template


class ControllableMonomer(Monomer, ABC):

    def __init__(self, team: Team, controller: str) -> None:
        super().__init__(team)
        self.user_id = controller

    async def parse_event(self, origin_event: ACTION_EVENT) -> dict[str, str | int]:
        event = copy.deepcopy(origin_event)
        if event["type"] == "harm.single":
            origin = event.pop("origin")
            target = event.pop("target")
            event["target_team"] = await target.team.get_team_name(self.user_id)
            event["target_name"] = await target.get_name(self.user_id)
            event["origin_team"] = await origin.team.get_team_name(self.user_id)
            event["origin_name"] = await origin.get_name(self.user_id)
        return event

    async def get_fight_stats(self) -> bytes:
        events = self.team.get_action_events()
        l = 0
        template_body = {
            "action_log": [await self.parse_event(event) for event in events],
            "monomers": [
                {
                    "index": (l := l + 1),
                    "name": await monomer.get_name(self.user_id),
                    "team": await monomer.get_team().get_team_name(self.user_id),
                }
                for monomer in self.get_team().scheduler.get_sorted_monomers()
            ],
            "me": {}, # TODO
            "lang": {} # TODO
        }
        return await render_template(
            "fight_log.html.jinja",
            await lang.text("log.title", self.user_id),
            self.user_id,
            template_body
        )



    async def on_action(self, teams: list[Team]) -> None:
        pass
