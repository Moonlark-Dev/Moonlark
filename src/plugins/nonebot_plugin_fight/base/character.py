import math
from abc import ABC, abstractmethod
from typing import Optional
from ..base.team import ControllableTeam
from ..types import CharacterData
from .controllable import ControllableMonomer
from ..lang import lang
from ..utils import level


class Character(ControllableMonomer, ABC):

    def has_final_skill(self) -> bool:
        return True

    def __init__(self, team: ControllableTeam, data: CharacterData) -> None:
        self.character_data = data
        self.equipments = []
        self.origin_hp = 900
        super().__init__(team)
        self.health = self.character_data["current_hp"]

    def set_attack(self, origin_attack: int = 78) -> None:
        self.attack = 3 * level.weapon.get_current_level(self.character_data["weapon"]["experience"])["level"] + origin_attack
        self.attack *= 92 / origin_attack
        self.attack *= 1.03 * math.log(self.get_level() + 10, 10)
        self.attack = round(self.attack)


    async def setup_equipments(self) -> None:
        pass


    async def get_text(self, key: str, *args, user_id: Optional[str] = None, **kwargs) -> str:
        key_name = self.get_character_id()[1]
        return await lang.text(f"characters.{key_name}.{key}", user_id or self.user_id, *args, **kwargs)

    @staticmethod
    @abstractmethod
    def get_character_id() -> tuple[int, str]:
        pass

    def get_level(self, allow_lv0: bool = True) -> int:
        return max(not allow_lv0, level.character.get_current_level(self.character_data["experience"])["level"])

    def get_max_hp(self) -> int:
        origin_hp = 900 + 350 * math.log(self.get_level(False),10)
        max_hp = origin_hp
        for equipment in self.equipments:
            max_hp = equipment.get_max_hp(origin_hp, max_hp)
        return max_hp

    async def get_name(self, user_id: str) -> str:
        return await self.get_text("name", user_id=user_id)


