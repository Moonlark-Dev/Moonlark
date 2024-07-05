from typing import TYPE_CHECKING, Any, Self

from nonebot import logger

from ..exceptions import NotUseableError
from ..types import DictItemData
from .useable import UseableItem

if TYPE_CHECKING:
    from .item import Item


class ItemStack:

    item: "Item"
    count: int
    data: dict
    user_id: str

    def __init__(self, item: "Item", count: int, data: dict, user_id: str):
        self.item = item
        self.count = count
        self.data = data
        self.user_id = user_id

    def getNbt(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def isUseable(self):
        return self.item.isUseable(self)

    async def getName(self):
        return await self.item.getName(self)

    async def getDescription(self) -> str:
        return await self.item.getDescription(self)

    def getDict(self) -> DictItemData:
        return {"count": self.count, "data": self.data, "item_id": self.item.getLocation().getItemID()}

    def isAddable(self) -> bool:
        return self.count < self.item.getProperties()["max_stack"]

    def getAddableAmount(self, max_count: int) -> int:
        return max(0, min(max_count, self.item.getProperties()["max_stack"] - self.count))

    async def use(self, *args, **kwargs) -> Any:
        if self.isUseable() and isinstance(self.item, UseableItem):
            ret = await self.item.useItem(self, *args, **kwargs)
            if "count" in kwargs and not self.item.getProperties()["multi_use"]:
                self.count -= kwargs["count"]
            logger.debug(f"用户 {self.user_id} 使用物品 {self.item.getLocation().getItemID()}，参数 {args}，返回 {ret}")
            return ret
        raise NotUseableError

    def compare(self, other: Self, ignore_nbt: list = []) -> bool:
        ignore = {}
        for key in ignore_nbt:
            ignore[key] = None
        return str(other.item.getLocation()) == str(self.item.getLocation()) and (self.data | ignore) == (
            other.data | ignore
        )
