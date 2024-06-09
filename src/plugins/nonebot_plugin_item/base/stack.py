from typing import TYPE_CHECKING, Any

from ..exceptions import NotUseableError
from ..types import DictItemData
from .useable import UseableItem

if TYPE_CHECKING:
    from .item import Item


class ItemStack:

    item: Item
    count: int
    data: dict
    user_id: str

    def __init__(self, item: "Item", count: int, data: dict, user_id: str):
        self.item = item
        self.count = count
        self.data = data
        self.user_id = user_id

    def isUseable(self):
        return self.item.isUseable(self)

    async def getName(self):
        return await self.item.getName(self)

    def getDict(self) -> DictItemData:
        return {
            "count": self.count,
            "data": self.data,
            "item_id": self.item.getLocation().getItemID()
        }

    async def use(self, *args, **kwargs) -> Any:
        if self.isUseable() and isinstance(self.item, UseableItem):
            return await self.item.useItem(self, *args, **kwargs)
        raise NotUseableError
