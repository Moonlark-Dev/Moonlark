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

from ...nonebot_plugin_larkuser.utils.waiter2 import WaitUserInput
from .monomer import Monomer, Team, ACTION_EVENT
from ..lang import lang
import copy
from typing import Optional
from ..types import ACTION_EVENT
from abc import ABC
from nonebot_plugin_alconna import UniMessage
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
                    "stat": await lang.text(
                        "stat",
                        self.user_id,
                        monomer.get_hp(),
                        round(monomer.get_hp() / monomer.get_max_hp()),
                        monomer.balance,
                    ),
                }
                for monomer in self.get_team().scheduler.get_sorted_monomers()
            ],
            "me": {
                "health": await lang.text(
                    "hp.normal",
                    self.user_id,
                    self.get_hp(),
                    self.get_max_hp(),
                    round(self.get_hp() / self.get_max_hp() * 100),
                ),
                "balance": self.balance,
                "power": 0,  # TODO 跟随大招系统制作
                "team_skill_point": await lang.text("skill_point", self.user_id, *self.team.get_skill_point()),
            },
            "lang": {
                "missed": await lang.text("log.missed", self.user_id),
                "action_title": await lang.text("log.action.title", self.user_id),
                "action_num": await lang.text("log.action.number", self.user_id),
                "action_stat": await lang.text("log.action.stat", self.user_id),
                "stat_title": await lang.text("log.stat.title", self.user_id),
                "stat_hp": await lang.text("log.stat.hp", self.user_id),
                "stat_balance": await lang.text("log.stat.balance", self.user_id),
                "stat_power": await lang.text("log.stat.power", self.user_id),
                "stat_team_skill_point": await lang.text("log.stat.skill", self.user_id),
            },
            "buff_log": [],  # TODO 等待 Buff 系统
        }
        return await render_template(
            "fight_log.html.jinja", await lang.text("log.title", self.user_id), self.user_id, template_body
        )

    async def on_action(self, teams: list[Team]) -> None:
        await UniMessage().image(raw=await self.get_fight_stats()).send()
        while await self.choose_skill():
            pass

    async def choose_skill(self, teams: list[Team]) -> None:
        waiter = WaitUserInput(
            UniMessage.text(text=await lang.text("controllable.options", self.user_id)),  # 细节等更多东西做出来再优化
            self.user_id,
            lambda s: int(s) in [1, 2, 9],
            "9",
        )
        await waiter.wait()
        result = await waiter.get(lambda m: int(m))
        if result == 1:
            await on_simple_attack(teams)
            self.team.add_skill_points()
        elif result == 2:
            if self.team.get_skill_point()[0] >= 1:
                await self.on_special_skill(teams)
                self.team.reduce_skill_points()
            else:
                await lang.send("option.no_skill_point", self.user_id)
                return True
        else:
            await lang.send("option.skipped", self.user_id)
            self.team.add_skill_points()

    @abstractmethod
    async def on_simple_attack(self, teams: list[Team]) -> None:
        pass

    @abstractmethod
    async def on_special_skill(self, teams: list[Team]) -> None:
        pass

    async def select_monomer(self, teams: list[Team]) -> Optional[Monomer]:
        if len(teams) == 0:
            return None  # no monomer to select
        while (team := await self.choose_team(teams)) is not None:
            while (monomer := await self.choose_monomer(team)) is not None:
                return monomer

    async def choose_monomer(self, team: Team) -> Optional[Monomer]:
        text = await lang.text("select.monomer", self.user_id)
        # TODO

    async def choose_team(self, teams: list[Team]) -> Optional[Team]:
        if len(teams) == 1:
            return teams[0]
