from .item import get_bag_items
from ...nonebot_plugin_item.registry.registry import ResourceLocation
from ..item import BagItem

ALL = -1


class ItemNotEnough(Exception):

    def __init__(self, need: int, have: int, user_id: str) -> None:
        self.need = need
        self.have = have
        self.user_id = user_id

    def __str__(self) -> str:
        return f"Not enough item: need {self.need}, but have {self.have} in user {self.user_id}'s bag."


async def get_bag_item_count(items: list[BagItem], location: ResourceLocation) -> int:
    count = 0
    for item in items:
        if item.stack.item.getLocation() == location:
            count += item.stack.count
    return count


async def remove_item_from_bag(user_id: str, location: ResourceLocation, count: int) -> None:
    bag_items = await get_bag_items(user_id)
    if (item_count := await get_bag_item_count(bag_items, location)) < count:
        raise ItemNotEnough(count, item_count, user_id)
    if count == ALL:
        count = item_count
    for item in bag_items:
        if item.stack.item.getLocation() == location:
            c = min(count, item.stack.count)
            item.stack.count -= c
            count -= c
        if count <= 0:
            break
