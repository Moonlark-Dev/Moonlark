from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from .monomer import Monomer


class Equipment(ABC):
    
    def __init__(self, experience: int, gains: dict[str, Any], monomer: "Monomer") -> None:
        self.experience = experience
        self.gains: dict[str, Any] = gains
        self.monomer = monomer
    

    @abstractmethod
    async def get_name() -> str:
        pass

    @abstractmethod
    async def setup() -> str:
        pass