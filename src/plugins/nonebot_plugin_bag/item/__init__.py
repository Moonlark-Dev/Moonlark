import asyncio
import json
from typing import Any
from nonebot_plugin_orm import AsyncSession, get_session
from sqlalchemy import select

from ..exceptions import ItemLockedError

from ..models import Bag
from nonebot_plugin_items.base.stack import ItemStack


class BagItem:

    def __init__(self, stack: ItemStack, index: int) -> None:
        self.stack = stack
        self.index = index
        self.is_locked = False

    async def get_item(self, session: AsyncSession) -> Bag:
        result = await session.scalar(select(Bag).where(Bag.user_id == self.stack.user_id, Bag.bag_index == self.index))
        if result is None:
            raise IndexError(f"Item ({self.stack.user_id=}, {self.index=}) not found.")
        return result

    async def set_item_index(self, index: int) -> None:
        async with get_session() as session:
            result = await self.get_item(session)
            result.bag_index = index
            await session.commit()
        self.index = index

    async def setup_bag_lock(self) -> None:
        async with get_session() as session:
            result = await self.get_item(session)
            if result.locked:
                raise ItemLockedError(f"Item ({self.stack.user_id=}, {self.index=}) is already locked.")
            result.locked = True
            await session.commit()
        self.is_locked = True

    async def save_item(self) -> None:
        async with get_session() as session:
            result = await self.get_item(session)
            result.data = json.dumps(self.stack.data)
            result.count = self.stack.count
            await session.commit()

    async def unlock_item(self) -> None:
        async with get_session() as session:
            result = await self.get_item(session)
            result.locked = False
            await session.commit()
        self.is_locked = False

    async def check_count(self) -> None:
        if self.stack.count > 0:
            return
        await self.drop()

    async def drop(self) -> None:
        async with get_session() as session:
            result = await self.get_item(session)
            await session.delete(result)
            await session.commit()
        self.is_locked = False
        del self

    async def on_delete(self) -> None:
        await self.save_item()
        await self.unlock_item()
        await self.check_count()

    def __del__(self) -> None:
        if self.is_locked:
            asyncio.create_task(self.on_delete())
