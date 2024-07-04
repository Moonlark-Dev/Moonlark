from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any
from .properties import ItemProperties, get_properties
from .item import Item

if TYPE_CHECKING:
    from .stack import ItemStack


class UseableItem(Item, ABC):

    def __init__(self, properties: ItemProperties = get_properties()) -> None:
        super().__init__(properties)
        self.properties["useable"] = True

    @abstractmethod
    async def useItem(self, stack: "ItemStack", *args, **kwargs) -> Any:
        pass
