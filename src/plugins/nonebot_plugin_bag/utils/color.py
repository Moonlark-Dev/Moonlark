from ..__main__ import lang
from ..commands.bag import STAR_COLORS
from nonebot_plugin_items.base.stack import ItemStack


from typing import Any


async def color_common_item_list(item_list: list[ItemStack], user_id: str) -> list[dict[str, Any]]:
    index = 0
    return [
        {
            "name": await item.getName(),
            "count": await lang.text("list.count", user_id, item.count),
            "index": await lang.text("list.index", user_id, index := index + 1),
            "text_color": STAR_COLORS[item.item.getProperties()["star"]],
        }
        for item in item_list
    ]