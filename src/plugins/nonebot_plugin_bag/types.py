from datetime import datetime
from typing_extensions import TypedDict

from nonebot_plugin_items.types import DictItemData

from nonebot_plugin_items.base.stack import ItemStack


class OverflowItem(TypedDict):
    index: int
    item: ItemStack
    time: datetime


class GivenItemsData(TypedDict):
    vimcoin: float
    experience: int
    items: list[DictItemData]
