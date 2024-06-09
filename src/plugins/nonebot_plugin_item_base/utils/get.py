from typing import Any
from ..stack import ItemStack
from ..registry.registry import ResourceLocation


async def get_item(item_id: ResourceLocation, count: int, data: dict[str, Any], user_id: str) -> ItemStack