from datetime import datetime, timedelta
from typing import Optional

from .team import ControllableTeam, Team
from .monomer import Monomer
from ..types import ACTION_EVENT, HarmData


class Scheduler:

    def __init__(self, time_to_draw: datetime) -> None:
        self.teams: list["Team"] = []
        self.time_to_draw = time_to_draw

    def register_team(self, team: "Team") -> "Scheduler":
        if len(self.teams) > 1:
            raise ValueError("The number of teams is limited to 2.")
        self.teams.append(team)
        return self

    async def post_action_event(self, event: ACTION_EVENT):
        for t in self.teams:
            await t.got_event(event)

    async def post_attack_event(self, origin: "Monomer", harms: list[HarmData]) -> None:
        await self.post_action_event({"type": "harm.single", "origin": origin, "harms": harms})

    def get_monomers(self) -> list["Monomer"]:
        monomers = []
        for team in self.teams:
            monomers += team.get_monomers()
        return monomers

    async def setup(self) -> None:
        if not any([True for t in self.teams if isinstance(t, ControllableTeam)]):
            raise TypeError("No controllable team found.")
        for monomer in self.get_monomers():
            await monomer.setup(self.get_selectable_teams(monomer))

    def get_another_team(self, team: "Team") -> "Team":
        return self.teams[0] if team == self.teams[1] else self.teams[1]

    def get_selectable_teams(self, monomer: "Monomer") -> list["Team"]:
        return [t for t in self.teams if t != monomer.get_team() and t.is_selectable()]

    async def get_actionable_monomers(self) -> list["Monomer"]:
        return [m for m in self.get_monomers() if await m.is_actionable()]

    async def get_sorted_monomers(self) -> list["Monomer"]:
        return sorted(await self.get_actionable_monomers(), key=lambda target: target.get_action_value())

    async def get_action_monomer(self) -> "Monomer":
        monomers = await self.get_sorted_monomers()
        action_monomer = monomers.pop(0)
        for monomer in monomers:
            monomer.reduce_action_value(action_monomer.get_action_value())
        action_monomer.reset_action_value()
        return action_monomer

    def get_remain_time(self) -> timedelta:
        return self.time_to_draw - datetime.now()

    async def loop(self) -> Optional[Team]:
        while await self.is_continuable():
            action_monomer = await self.get_action_monomer()
            await action_monomer.action(self.get_selectable_teams(action_monomer))
            if self.get_remain_time().total_seconds() < 0:
                return None
        return (await self.get_actionable_team())[0]

    async def is_continuable(self) -> bool:
        return len(await self.get_actionable_team()) > 1

    async def get_actionable_team(self) -> list["Team"]:
        teams = []
        for team in self.teams:
            actionable_monomers = [m for m in team.get_monomers() if await m.is_actionable()]
            if len(actionable_monomers) >= 1:
                teams.append(team)
        return teams
