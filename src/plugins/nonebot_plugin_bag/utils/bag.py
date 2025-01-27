from nonebot_plugin_orm import get_session
import base64
import json

from nonebot_plugin_items.utils.get import get_item

from ..models import BagOverflow
from .overflow import get_overflow_item

from sqlalchemy import select
from nonebot_plugin_larkuser import get_user
from .overflow import put_overflow_item
from nonebot.log import logger
from ..config import config
from .item import get_bag_item
from .item import get_bag_items, get_items_count
from nonebot_plugin_items.base.stack import ItemStack
from ..models import Bag
from typing import Any


async def give_special_item(user_id: str, name: str, count: int, data: dict[str, Any]) -> None:
    user = await get_user(user_id)
    match name:
        case "experience":
            await user.add_experience(count)
        case "vimcoin":
            await user.add_vimcoin(count)
        case "fav":
            await user.add_fav(count / data.get("multiple", 100))
        case _:
            raise ValueError(f"{name} is not a valid special item name")


async def get_free_index(user_id: str) -> int:
    """获取空闲背包索引

    Args:
        user_id (str): 用户ID

    Returns:
        int: 背包索引
    """
    index = 1
    while True:
        try:
            await get_bag_item(user_id, index, ignore_lock=True)
        except IndexError:
            break
        index += 1
    return index


async def append_item(user_id: str, item: ItemStack, count: int) -> None:
    logger.debug(f"{user_id=} {item=}")
    if (await get_items_count(user_id)) >= config.bag_max_size:
        return await put_overflow_item(item)
    logger.debug("Adding item into bag.")
    bag_index = await get_free_index(user_id)
    logger.debug(f"Bag index: {bag_index}")
    async with get_session() as session:
        session.add(
            Bag(
                user_id=user_id,
                item_id=str(item.item.getLocation()),
                count=count,
                bag_index=bag_index,
                data=base64.b64encode(json.dumps(item.data).encode("utf-8")),
                locked=False,
            )
        )
        await session.commit()


async def give_item(user_id: str, item: ItemStack) -> None:
    if item.item.getLocation().getNamespace() == "special":
        return await give_special_item(user_id, item.item.getLocation().getPath(), item.count, item.data)
    count = item.count
    logger.debug(f"{item=}")
    for bag_item in await get_bag_items(user_id):
        if bag_item.stack.compare(item) and bag_item.stack.isAddable():
            r = bag_item.stack.getAddableAmount(item.count)
            bag_item.stack.count += r
            count -= r
        if count == 0:
            break
    logger.debug(f"{count=}")
    if count > 0:
        await append_item(user_id, item, count)
    logger.debug(f"Item added: {item}")


async def take_overflow_item(user_id: str, index: int) -> None:
    async with get_session() as session:
        result = await session.scalar(select(BagOverflow).where(BagOverflow.id_ == index))
        if result is None:
            raise IndexError(f"Item {index} not found.")
        await give_item(user_id, (await get_overflow_item(index))["item"])
        await session.delete(result)
        await session.commit()
