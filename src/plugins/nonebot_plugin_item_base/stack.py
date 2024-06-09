from operator import is_
from typing import TYPE_CHECKING, Any

from .exceptions import NotUseableError


if TYPE_CHECKING:
    from .item import Item


class ItemStack:

    def __init__(self, item: "Item", count: int, user_id: str) -> None:
        self.item = item
        self.count = count
        self.user_id = user_id

    async def setup_data(self, data: dict[str, Any]) -> None:
        self.data = await self.item.setup_data(data, self.user_id)
    
    def compare(self, other: "ItemStack") -> bool:
        return self.item == other.item and self.data == other.data

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, ItemStack) and self.compare(other)

    async def __call__(self, *args: Any, **kwds: Any) -> Any:
        if await self.is_useable():
            return await self.item.use_item(self, args, kwds)
        raise NotUseableError
    
    async def get_display_name(self) -> str:
        return await self.item.get_display_name(self)
    
    async def get_description(self) -> str:
        return await self.item.get_description(self)
    
    async def is_useable(self) -> bool:
        return await self.item.is_useable(self)
