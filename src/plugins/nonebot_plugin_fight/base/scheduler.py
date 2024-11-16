from .team import Team
from .monomer import Monomer


class Scheduler:

    def __init__(self, teams: list[Team]) -> None:
        self.teams = teams

    def get_monomers(self) -> list[Monomer]:
        monomers = []
        for team in self.teams:
            monomers += team.get_monomers()
        return monomers

    async def setup(self) -> None:
        for m in self.get_monomers():
            await m.setup(self.get_selectable_teams())

    def get_selectable_teams(self, monomer: Monomer) -> list[Team]:
        return [t for t in self.teams if t != monomer.get_team() and t.is_selectable()]

    def get_actionable_monomers(self) -> list[Monomer]:
        return [m for m in self.get_monomers() if m.is_actionable()]

    def get_action_monomer(self) -> Monomer:
        monomers = sorted(self.get_actionable_monomers(), key=lambda m: m.get_action_value())
        action_monomer = monomers.pop(0)
        for m in monomers:
            m.reduce_action_value(action_monomer.get_action_value())
        action_monomer.reset_action_value()
        return action_monomer

    async def loop(self) -> None:
        while self.is_continuable():
            action_monomer = self.get_action_monomer()
            await action_monomer.on_action(self.get_selectable_teams(action_monomer))

    def is_continuable(self) -> bool:
        return len(self.get_actionable_team()) > 1

    def get_actionable_team(self) -> list[Team]:
        teams = []
        for team in self.teams:
            actionable_monomers = [m for m in team.get_monomers() if m.is_actionable()]
            if len(actionable_monomers) >= 1:
                teams.append(team)
        return teams
