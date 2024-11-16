from .team import Team
from .monomer import Monomer

from ..types import ACTION_EVENT


class Scheduler:

    def __init__(self) -> None:
        self.teams = []

    def register_team(self, team: Team) -> "Scheduler":
        self.teams.append(team)
        return self

    async def post_action_event(self, event: ACTION_EVENT):
        for t in self.teams:
            await t.get_event(event)

    async def post_attack_event(
        self, target: Monomer, origin: Monomer, harm: int, harm_type: str, missed: bool = False
    ) -> None:
        data = {
            "type": "harm.single",
            "origin": origin,
            "target": target,
            "harm_value": harm,
            "harm_type": harm_type,
            "harm_missed": missed,
        }
        await self.post_action_event(data)

    def get_monomers(self) -> list[Monomer]:
        monomers = []
        for team in self.teams:
            monomers += team.get_monomers()
        return monomers

    async def setup(self) -> None:
        for monomer in self.get_monomers():
            await monomer.setup(self.get_selectable_teams(monomer))

    def get_selectable_teams(self, monomer: Monomer) -> list[Team]:
        return [t for t in self.teams if t != monomer.get_team() and t.is_selectable()]

    def get_actionable_monomers(self) -> list[Monomer]:
        return [m for m in self.get_monomers() if m.is_actionable()]

    def get_sorted_monomers(self) -> list[Monomer]:
        return sorted(self.get_actionable_monomers(), key=lambda target: target.get_action_value())

    def get_action_monomer(self) -> Monomer:
        monomers = self.get_sorted_monomers()
        action_monomer = monomers.pop(0)
        for monomer in monomers:
            monomer.reduce_action_value(action_monomer.get_action_value())
        action_monomer.reset_action_value()
        return action_monomer

    async def loop(self) -> None:
        while self.is_continuable():
            action_monomer = self.get_action_monomer()
            await action_monomer.action(self.get_selectable_teams(action_monomer))

    def is_continuable(self) -> bool:
        return len(self.get_actionable_team()) > 1

    def get_actionable_team(self) -> list[Team]:
        teams = []
        for team in self.teams:
            actionable_monomers = [m for m in team.get_monomers() if m.is_actionable()]
            if len(actionable_monomers) >= 1:
                teams.append(team)
        return teams
