from abc import ABC, abstractmethod
from typing import Any

from .stack import ItemStack


class Item(ABC):
    
    def __init__(self) -> None:
        pass
    

    @abstractmethod
    async def setup_data(self, data: dict[str, Any], user_id: int) -> dict[str, Any]:
        ...


    async def is_useable(self, data: dict[str, Any]) -> bool:
        return data.get("useable", True) and hasattr(self, "use_item")


    @abstractmethod
    async def use_item(self, stack: ItemStack, args: tuple[str], kwargs: dict[str, Any]) -> Any:
        ...
