from abc import ABC, abstractmethod
from src.plugins.nonebot_plugin_fight.base.team import ControllableTeam
from src.plugins.nonebot_plugin_fight.types import CharacterData
from .controllable import ControllableMonomer


class Character(ControllableMonomer, ABC):

    def __init__(self, team: ControllableTeam, data: CharacterData) -> None:
        super().__init__(team)
        self.character_data = data
        self.health = self.character_data["current_hp"]

    @staticmethod
    @abstractmethod
    def get_character_id() -> int:
        pass
