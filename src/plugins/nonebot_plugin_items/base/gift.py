from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from .item import Item
from .properties import ItemProperties, get_properties

if TYPE_CHECKING:
    from .stack import ItemStack


class GiftItem(Item, ABC):
    """
    礼物物品基类

    继承此类的物品可以作为礼物赠送给机器人，会触发好感度增加和 AI 回复。
    不再继承 UseableItem，不能通过 /bag use 使用。
    """

    fav_value: float = 0.005

    def __init__(self, properties: ItemProperties = get_properties()):
        super().__init__(properties)

    def isUseable(self, stack: "ItemStack") -> bool:
        return False

    @abstractmethod
    async def on_gift_used(self, stack: "ItemStack", **kwargs: Any) -> Any: ...

    async def getGiftPrompt(self, stack: "ItemStack", user_nickname: str) -> str:
        item_name = await self.getName(stack)
        description = await self.getDescription(stack)

        if description:
            return await self.lang.text(
                "gift.prompt_with_description", stack.user_id, user_nickname, item_name, description
            )
        return await self.lang.text("gift.prompt", stack.user_id, user_nickname, item_name)
