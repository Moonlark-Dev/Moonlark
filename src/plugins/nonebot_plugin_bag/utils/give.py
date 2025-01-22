from typing import Literal
from nonebot.log import logger
from ...nonebot_plugin_item.types import DictItemData
from ...nonebot_plugin_item.utils.string import get_location_by_id
from ...nonebot_plugin_item.utils.get import get_item
from ...nonebot_plugin_larkuser import get_user
from ..types import GivenItemsData
from .bag import give_item, give_special_item


async def give_item_by_data(user_id: str, items: GivenItemsData) -> None:
    user = await get_user(user_id)
    await user.add_vimcoin(items["vimcoin"])
    await user.add_experience(items["experience"])
    for item_data in items["items"]:
        location = get_location_by_id(item_data["item_id"])
        item = await get_item(location, user_id, item_data["count"], item_data["data"])
        await give_item(user_id, item)


"""
async def give_special_item(user_id: str, name: str, count: int) -> None:
    user = await get_user(user_id)
    match name:
        case "experience":
            await user.add_experience(count)
        case "vimcoin":
            await user.add_vimcoin(count)
        case _:
            raise ValueError(f"{name} is not a valid special item name")
"""


async def give_item_by_list(user_id: str, items: list[DictItemData]) -> None:
    for item_data in items:
        logger.debug(f"Current item: {item_data}")
        location = get_location_by_id(item_data["item_id"])
        if location.getNamespace() == "special":
            await give_special_item(user_id, location.getPath(), item_data["count"], item_data["data"])
            continue
        logger.debug(f"Location got: {location}")
        item = await get_item(location, user_id, item_data["count"], item_data["data"])
        logger.debug(f"Item got: {item}")
        await give_item(user_id, item)
