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
from .team import ControllableTeam
import re
from ..lang import lang
from typing import Any, Optional, Awaitable, Callable
from ..types import ACTION_EVENT, SkillInfo, ActionCommand
from abc import ABC, abstractmethod
from nonebot_plugin_alconna import UniMessage
from ...nonebot_plugin_render import render_template


class ControllableMonomer(Monomer, ABC):

    def __init__(self, team: ControllableTeam) -> None:
        super().__init__(team)
        if not isinstance(self.team, ControllableTeam):
            raise ValueError("The team must be an instance of ControllableTeam.")
        self.user_id = self.team.get_user_id()
        self.action_commands: list[ActionCommand] = []
        self.tiggered_commands = []
        self.skills: list[Callable[[None, Team], Awaitable[None]] | Callable[[Monomer, Team], Awaitable[None]]] = []

    def append_action_command(self, command: ActionCommand) -> None:
        self.action_commands.append(command)

    @abstractmethod
    async def get_skill_info_list(self) -> list[SkillInfo]:
        return []

    def tigger_command_after(self, command: ActionCommand, after: ActionCommand | None) -> None:
        self.tiggered_commands.append((command, after))

    async def on_action(self, teams: list[Team]) -> None:
        while len(self.action_commands) > 0:
            command = self.action_commands.pop(0)
            func = self.skills[command["skill_index"]]
            await func(command["target"], teams[0]) # type: ignore
            if command["skill_info"]["occupy_round"]:
                break


def get_monomer_indexs(monomer: ControllableMonomer, monomers: list[ControllableMonomer]) -> list[int]:
    indexs = []
    for i, m in enumerate(monomers):
        if m == monomer:
            indexs.append(i)
    return indexs


class ControllableRoundBoundary(Monomer):

    def __init__(self, team: ControllableTeam) -> None:
        super().__init__(team)
        if not isinstance(self.team, ControllableTeam):
            raise ValueError("The team must be an instance of ControllableTeam.")
        self.team: ControllableTeam = team
        self.user_id = self.team.get_user_id()

    def sort_momomers_by_action_rank(self) -> list[ControllableMonomer]:
        monomers = []
        controllable_monomers = []
        scheduler = self.get_team().scheduler
        for monomer in self.team.get_monomers():
            if isinstance(monomer, ControllableMonomer):
                controllable_monomers.append(monomer)
        for monomer in scheduler.get_sorted_monomers():
            if monomer in controllable_monomers:
                monomers.append(monomer)
            elif isinstance(monomer, ControllableRoundBoundary):
                break
        return monomers

    def is_selectable(self) -> bool:
        return False

    async def get_skill_info(self, skill: SkillInfo) -> str:
        return " ".join(
            t
            for t in [
                await lang.text("skill_stat.cost", self.user_id, skill["cost"]) if skill["cost"] > 0 else "",
                await lang.text("skill_stat.not_occupy_round", self.user_id) if skill["occupy_round"] == 0 else "",
            ]
            if t
        )

    async def on_action(self, teams: list[Team]) -> None:
        self.reset_speed()
        monomers = self.sort_momomers_by_action_rank()
        skills = await fetch_skills_from_monomers(monomers)
        template_body = {
            "monomers_current_team": [
                {
                    "index": ", ".join(map(str, get_monomer_indexs(monomer, monomers))),
                    "name": await monomer.get_name(self.user_id),
                    "stat": await self.team.get_monomer_stat(monomer),
                    "skills": [
                        {"index": i + 1, "name": skill["name"], "info": await self.get_skill_info(skill)}
                        for i, skill in enumerate(skills)
                        if skill["monomer"] == monomer
                    ],
                }
                for monomer in monomers
            ],
            "another_name": await teams[0].get_team_name(self.user_id),
            "monomers_another_team": [
                {
                    "index": teams[0].get_monomers().index(monomer) + 1,
                    "name": await monomer.get_name(self.user_id),
                    "stat": await self.team.get_monomer_stat(monomer),
                }
                for monomer in teams[0].get_monomers()
                if monomer.is_selectable()
            ],
            "lang": {
                "another_name": await lang.text("action.another_name", self.user_id),
                "myteam": await lang.text("action.myteam", self.user_id),
            },
        }
        image = await render_template(
            "fight_skill_list.html.jinja", await lang.text("action.title", self.user_id), self.user_id, template_body
        )
        message = UniMessage().image(raw=image)
        commands = []
        while True:
            waiter = WaitUserInput(
                message,
                self.user_id,
                lambda string: re.match(r"^[0-9a-z \.]+$", string) is not None
                and parse_action_command(string, skills, monomers, teams[0]) is not None,
            )
            await waiter.wait()
            commands = waiter.get(lambda string: parse_action_command(string, skills, monomers, teams[0]))
            if commands is None or not self.check_action_commands(commands, monomers, teams[0]):
                message = UniMessage.text(text=await lang.text("action.invalid", self.user_id))
                continue
            break
        self.process_commands(commands)

    def process_commands(self, commands: list[ActionCommand]) -> None:
        for command in commands:
            if not isinstance(command["skill_info"]["monomer"], ControllableMonomer):
                continue
            if not command["skill_info"]["instant"]:
                command["skill_info"]["monomer"].append_action_command(command)
            else:
                command["skill_info"]["monomer"].tigger_command_after(
                    command, commands[commands.index(command) - 1] if commands.index(command) > 0 else None
                )

    def reset_speed(self) -> int:
        total_speed = 0
        for monomer in self.team.get_monomers():
            total_speed += monomer.speed
        self.speed = round(total_speed / len(self.team.get_monomers()) * 0.9)
        return self.speed

    async def get_sorted_momoners_stat(self) -> list[dict[str, Any]]:
        index = 0
        return [
            {
                "index": (index := index + 1),
                "name": await monomer.get_name(self.user_id),
                "team": await monomer.get_team().get_team_name(self.user_id),
                "stat": await self.team.get_monomer_stat(monomer),
            }
            for monomer in self.team.scheduler.get_sorted_monomers()
            if not isinstance(monomer, ControllableRoundBoundary)
        ]

    async def get_fight_log(self) -> UniMessage:
        events = self.team.get_action_events()
        template_body = {
            "action_log": [await self.team.parse_event(event) for event in events],
            "monomers": await self.get_sorted_momoners_stat(),
            "lang": {
                "missed": await lang.text("log.missed", self.user_id),
                "action_title": await lang.text("log.action.title", self.user_id),
                "action_num": await lang.text("log.action.number", self.user_id),
                "action_stat": await lang.text("log.action.stat", self.user_id),
            },
        }
        image = await render_template(
            "fight_log.html.jinja", await lang.text("log.title", self.user_id), self.user_id, template_body
        )
        return UniMessage().image(raw=image)

    def check_action_commands(
        self, commands: list[ActionCommand], monomers: list[ControllableMonomer], enemy_team: Team
    ) -> bool:
        monomer_action_count = {}
        points, max_skill_point = self.team.get_skill_point()
        for command in commands:
            if command["skill_info"]["instant"] or not command["skill_info"]["occupy_round"]:
                continue
            monomer_action_count[command["skill_info"]["monomer"]] = 1 + monomer_action_count.get(
                command["skill_info"]["monomer"], 0
            )
        for monomer, count in monomer_action_count.items():
            if monomers.count(monomer) < count:
                return False
        for command in commands:
            if not command["skill_info"]["instant"]:
                break
            points -= command["skill_info"]["cost"]
            points = min(points, max_skill_point)
            if points < 0:
                return False
        for monomer in monomers:
            for command in [
                cmd for cmd in commands if cmd["skill_info"]["monomer"] == monomer and not cmd["skill_info"]["instant"]
            ]:
                points -= command["skill_info"]["cost"]
                if points < 0:
                    return False
                if command["skill_info"]["cost"] == 0 and command["skill_info"]["occupy_round"]:
                    points += 1
                points = min(points, max_skill_point)
                for cmd in [cmd for cmd in commands[commands.index(command) :]]:
                    if not cmd["skill_info"]["instant"]:
                        break
                    points -= command["skill_info"]["cost"]
                    points = min(points, max_skill_point)
                    if points < 0:
                        return False
        return True


async def fetch_skills_from_monomers(monomers: list[ControllableMonomer]) -> list[SkillInfo]:
    skills = []
    processed_monomer = []
    for monomer in monomers:
        if monomer in processed_monomer or not isinstance(monomer, ControllableMonomer):
            continue
        processed_monomer.append(monomer)
        for skill in await monomer.get_skill_info_list():
            skills.append(skill)
    return skills


def parse_action_command(
    string: str, skills: list[SkillInfo], monomers: list[ControllableMonomer], enemy_team: Team
) -> Optional[list[ActionCommand]]:
    unparsed_commands = [s for s in string.split(" ") if s != ""]
    commands: list[ActionCommand] = []
    while len(unparsed_commands) == 0:
        command = unparsed_commands.pop(0)
        if command in ["fin", "finish", "ok", "k"]:
            return commands
        elif command.replace(".", "", 1).isdigit():
            skill_index, target_index = map(int, command.split("."))
        elif command.isdigit():
            skill_index = int(command)
            target_index = None
        else:
            return None
        skill_index -= 1
        if skill_index < 0 or skill_index >= len(skills):
            return None
        skill = skills[skill_index]
        if (
            skill["target_type"] != "none"
            and target_index is None
            and len(unparsed_commands) > 0
            and unparsed_commands[0].isdigit()
        ):
            target_index = int(unparsed_commands.pop(0))
        elif target_index is None:
            return None
        try:
            if skill["target_type"] == "self":
                target = monomers[target_index]
            elif skill["target_type"] == "enemy":
                target = enemy_team.get_monomers()[target_index]
            else:
                target = None
        except IndexError:
            return None
        offset = len([s for s in skills if s["monomer"] == monomers[0] and skills.index(s) < skill_index])
        commands.append({"skill_index": skill_index - offset, "target": target, "skill_info": skill})
    return commands
