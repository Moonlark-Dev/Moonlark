from abc import ABC, abstractmethod
from typing import Any

from .registry.registry import ResourceLocation

from .stack import ItemStack


class Item(ABC):


    def __init__(self, item_id: ResourceLocation) -> None:
        self.item_id = item_id

    async def setup_data(self, data: dict[str, Any], user_id: str) -> dict[str, Any]:
        return data | {"user_id": user_id}

    async def is_useable(self, stack: ItemStack) -> bool:
        return True

    @abstractmethod
    async def use_item(self, stack: ItemStack, args: tuple[str], kwargs: dict[str, Any]) -> Any:
        ...

    @abstractmethod
    async def get_display_name(self, stack: ItemStack) -> str:
        ...

    @abstractmethod
    async def get_description(self, stack: ItemStack) -> str:
        ...


