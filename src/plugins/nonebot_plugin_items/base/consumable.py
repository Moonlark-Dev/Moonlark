from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .item import Item

if TYPE_CHECKING:
    from .stack import ItemStack


class ConsumableItem(Item, ABC):
    """消耗品基类。

    继承此类的物品（注册时 properties 需带 ``useable=True``）会出现在
    ``/consumables`` 列表中，每次使用消耗一个，效果由 ``on_use`` 实现。
    """

    @abstractmethod
    async def on_use(self, stack: "ItemStack") -> str | None:
        """消耗一个物品并应用效果，返回结果文本（None 表示无文本）"""
