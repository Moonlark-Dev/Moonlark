from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .monomer import Monomer


class Equipment(ABC):

    def __init__(self, experience: int, gains: dict[str, Any], monomer: "Monomer") -> None:
        self.experience = experience
        self.gains: dict[str, Any] = gains
        self.monomer = monomer


    @staticmethod
    @abstractmethod
    async def get_name() -> str:
        pass

    @abstractmethod
    async def setup(self) -> str:
        pass

    def get_max_hp(self, origin_max_hp: int, current_max_hp: int) -> int:
        return current_max_hp

