from typing import Any
from ..base.stack import ItemStack
from .. import registry


async def get_item(
    location: registry.ResourceLocation, user_id: str, count: int = 1, data: dict[str, Any] = {}
) -> ItemStack:
    """通过 location 获取物品

    Args:
        location (registry.ResourceLocation): location
        user_id (str): 用户 ID（本地化需要）
        count (int, optional): 物品数量. Defaults to 1.
        data (dict[str, Any], optional): 物品NBT. Defaults to {}.

    Returns:
        ItemStack: 物品 Stack
    """
    item = registry.ITEMS.getValue(location)
    return ItemStack(item, count, data, user_id)
