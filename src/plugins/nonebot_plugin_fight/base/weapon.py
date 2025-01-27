from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .monomer import Monomer


class Weapon(ABC):

    def __init__(self, experience: int, talent_level: dict[str, int], damage: int, monomer: "Monomer") -> None:
        self.experience: int = experience
        self.talent_level: dict[str, int] = talent_level
        self.damage: int = damage
        self.monomer = monomer

    @abstractmethod
    async def get_name() -> str:
        pass

    @abstractmethod
    async def setup() -> str:
        pass
