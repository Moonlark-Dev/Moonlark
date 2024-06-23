from nonebot_plugin_orm import get_session
import base64
import json

from ...nonebot_plugin_item.utils.get import get_item

from ..models import BagOverflow
from .overflow import get_overflow_item

from sqlalchemy import select

from .overflow import put_overflow_item

from ..config import config
from .item import get_bag_item
from .item import get_bag_items
from ...nonebot_plugin_item.base.stack import ItemStack
from ..models import Bag


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
            await get_bag_item(user_id, index)
        except IndexError:
            break
    return index


async def append_item(user_id: str, item: ItemStack) -> None:
    if len(await get_bag_items(user_id)) >= config.bag_max_size:
        return await put_overflow_item(item)
    async with get_session() as session:
        session.add(
            Bag(
                user_id=user_id,
                item_id=str(item.item.getLocation()),
                count=item.count,
                bag_index=await get_free_index(user_id),
                data=base64.b64encode(json.dumps(item.data).encode("utf-8")),
                locked=False,
            )
        )
        await session.commit()


async def give_item(user_id: str, item: ItemStack) -> None:
    count = item.count
    for bag_item in await get_bag_items(user_id):
        if bag_item.stack.compare(item) and bag_item.stack.count < bag_item.stack.item.getProperties()["max_stack"]:
            bag_item.stack.count += (
                reduced := min(bag_item.stack.item.getProperties()["max_stack"] - bag_item.stack.count, item.count)
            )
            count -= reduced
        if count == 0:
            break
    if count > 0:
        await append_item(user_id, await get_item(item.item.getLocation(), user_id, count, item.data))


async def take_overflow_item(user_id: str, index: int) -> None:
    async with get_session() as session:
        result = await session.scalar(select(BagOverflow).where(BagOverflow.id_ == index))
        if result is None:
            raise IndexError(f"Item {index} not found.")
        await give_item(user_id, (await get_overflow_item(index))["item"])
        await session.delete(result)
        await session.commit()
