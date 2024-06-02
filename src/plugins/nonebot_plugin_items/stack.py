from operator import is_
from typing import TYPE_CHECKING, Any

from .exceptions import NotUseableError


if TYPE_CHECKING:
    from .item import Item


class ItemStack:

    def __init__(self, item: "Item") -> None:
        self.item = item

    async def setup_item(self, count: int, data: dict[str, Any], user_id: int) -> None:
        self.count = count
        self.data = await self.item.setup_data(data, user_id)
    
    def compare(self, other: "ItemStack") -> bool:
        return self.item == other.item and self.data == other.data

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, ItemStack) and self.compare(other)

    async def __call__(self, *args: Any, **kwds: Any) -> Any:
        if await self.item.is_useable(self.data):
            return await self.item.use_item(self, args, kwds)
        raise NotUseableError    
