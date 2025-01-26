from abc import ABC, abstractmethod
from typing import Any, Coroutine, Optional
from src.plugins.nonebot_plugin_fight.base.team import ControllableTeam
from src.plugins.nonebot_plugin_fight.types import CharacterData
from .controllable import ControllableMonomer
from ..lang import lang


class Character(ControllableMonomer, ABC):

    def __init__(self, team: ControllableTeam, data: CharacterData) -> None:
        super().__init__(team)
        self.character_data = data
        self.health = self.character_data["current_hp"]

    async def get_text(self, key: str, *args, user_id: Optional[str] = None, **kwargs) -> str:
        key_name = self.get_character_id()[1]
        return await lang.text(f"characters.{key_name}.{key}", user_id or self.user_id, *args, **kwargs)

    @staticmethod
    @abstractmethod
    def get_character_id() -> tuple[int, str]:
        pass

    async def get_name(self, user_id: str) -> str:
        return await self.get_text("name", user_id=user_id)