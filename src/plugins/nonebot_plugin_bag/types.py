from datetime import datetime
from typing import TypedDict

from ..nonebot_plugin_item.base.stack import ItemStack


class OverflowItem(TypedDict):
    index: int
    item: ItemStack
    time: datetime
