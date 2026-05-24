from typing import Any
from ..base.stack import ItemStack
from ..registry import ITEMS, ResourceLocation


async def get_item(
    location: ResourceLocation, user_id: str, count: int = 1, data: dict[str, Any] = {}
) -> ItemStack:
    """通过 location 获取物品

    Args:
        location (ResourceLocation): location
        user_id (str): 用户 ID（本地化需要）
        count (int, optional): 物品数量. Defaults to 1.
        data (dict[str, Any], optional): 物品NBT. Defaults to {}.

    Returns:
        ItemStack: 物品 Stack
    """
    item = ITEMS.getValue(location)
    return ItemStack(item, count, data, user_id)
