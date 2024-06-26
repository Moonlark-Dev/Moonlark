from datetime import datetime
from typing import TypedDict

from ..nonebot_plugin_item.types import DictItemData

from ..nonebot_plugin_item.base.stack import ItemStack


class OverflowItem(TypedDict):
    index: int
    item: ItemStack
    time: datetime


class GivenItemsData(TypedDict):
    vimcoin: float
    experience: int
    items: list[DictItemData]
