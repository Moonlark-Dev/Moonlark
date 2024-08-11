import base64
from nonebot.log import logger
import json
from nonebot_plugin_orm import get_session
from sqlalchemy import select
from ..exceptions import ItemLockedError
from ..item import BagItem
from ...nonebot_plugin_item.utils.string import get_location_by_id
from ...nonebot_plugin_item.utils.get import get_item
from ..models import Bag


async def get_bag_item(user_id: str, index: int, ignore_lock: bool = False) -> BagItem:
    """获取背包物品

    Args:
        user_id (str): 用户ID
        index (int): 物品索引编号
        ignore_lock (bool, optional): 是否忽略物品锁定. Defaults to False.

    Raises:
        IndexError: 找不到物品

    Returns:
        BagItem: 物品对象
    """
    async with get_session() as session:
        result = await session.scalar(select(Bag).where(Bag.user_id == user_id, Bag.bag_index == index))
        if result is None:
            raise IndexError(f"Item {user_id}->{index} not found.")
        item = await get_item(
            get_location_by_id(result.item_id), user_id, result.count, json.loads(base64.b64decode(result.data))
        )
        bag_item = BagItem(item, result.bag_index)
        if not ignore_lock:
            await bag_item.setup_bag_lock()
        return bag_item


async def get_bag_items(user_id: str, ignore_lock: bool = False, ignore_locked_item: bool = True) -> list[BagItem]:
    """获取用户背包物品列表

    Args:
        user_id (str): 用户ID
        ignore_lock (bool, optional): 是否忽略物品锁定. Defaults to False.
        ignore_locked_item (bool, optional): 忽略已锁定的物品（与 ignore_lock 同时设置的时忽略此设置）. Defaults to False.

    Returns:
        list[BagItem]: 物品列表
    """
    async with get_session() as session:
        result = await session.scalars(select(Bag.bag_index).where(Bag.user_id == user_id))
        item_list = []
        logger.debug(f"Getting bag items of user {user_id}")
        for index in result:
            try:
                item_list.append(await get_bag_item(user_id, index, ignore_lock))
            except IndexError as e:
                if not ignore_locked_item:
                    raise e
            except ItemLockedError as e:
                if not ignore_locked_item:
                    raise e
    return item_list


async def get_items_count(user_id: str) -> int:
    async with get_session() as session:
        result = await session.scalars(select(Bag.bag_index).where(Bag.user_id == user_id))
        return len(result.all())
