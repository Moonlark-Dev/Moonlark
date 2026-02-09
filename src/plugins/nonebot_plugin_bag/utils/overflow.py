from datetime import datetime
import json
from typing import AsyncGenerator
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from nonebot_plugin_items.base.stack import ItemStack
from ..config import config
from ..types import OverflowItem
from nonebot_plugin_items.utils.string import get_location_by_id
from nonebot_plugin_items.utils.get import get_item
from ..models import BagOverflow


async def get_overflow_item(index: int) -> OverflowItem:
    async with get_session() as session:
        item = await session.scalar(select(BagOverflow).where(BagOverflow.id_ == index))
        if item is None:
            raise IndexError(f"Item {index} not found.")
        return {
            "item": await get_item(get_location_by_id(item.item_id), item.user_id, item.count, json.loads(item.data)),
            "index": index,
            "time": item.time,
        }


async def get_overflow_items() -> AsyncGenerator[OverflowItem, None]:
    async with get_session() as session:
        result = await session.scalars(select(BagOverflow.id_))
    for index in result:
        yield await get_overflow_item(index)


async def put_overflow_item(item: ItemStack) -> None:
    async with get_session() as session:
        session.add(
            BagOverflow(
                item_id=str(item.item.getLocation()),
                count=item.count,
                data=json.dumps(item.data),
                user_id=item.user_id,
                time=datetime.now(),
            )
        )
        await session.commit()


async def is_item_takeable(user_id: str, index: int) -> bool:
    item = await get_overflow_item(index)
    return (
        item["item"].user_id == user_id
        or (datetime.now() - item["time"]).total_seconds() >= config.overflow_protect_hours * 3600
    )
