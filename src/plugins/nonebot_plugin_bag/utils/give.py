from typing import Literal
from ...nonebot_plugin_item.types import DictItemData
from ...nonebot_plugin_item.utils.string import get_location_by_id
from ...nonebot_plugin_item.utils.get import get_item
from ...nonebot_plugin_larkuser.utils.level import add_exp
from ...nonebot_plugin_larkuser.utils.vimcoin import add_vimcoin
from ..types import GivenItemsData
from .bag import give_item


async def give_item_by_data(user_id: str, items: GivenItemsData) -> None:
    await add_vimcoin(user_id, items["vimcoin"])
    await add_exp(user_id, items["experience"])
    for item_data in items["items"]:
        location = get_location_by_id(item_data["item_id"])
        item = await get_item(location, user_id, item_data["count"], item_data["data"])
        await give_item(user_id, item)


async def give_special_item(user_id: str, name: str, count: int) -> None:
    match name:
        case "experience":
            await add_exp(user_id, count)
        case "vimcoin":
            await add_vimcoin(user_id, count)
        case _:
            raise ValueError(f"{name} is not a valid special item name")


async def give_item_by_list(user_id: str, items: list[DictItemData]) -> None:
    for item_data in items:
        location = get_location_by_id(item_data["item_id"])
        if location.getNamespace() == "special":
            await give_special_item(user_id, location.getPath(), item_data["count"])
            continue
        item = await get_item(location, user_id, item_data["count"], item_data["data"])
        await give_item(user_id, item)
