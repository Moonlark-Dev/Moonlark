import asyncio
import base64
import json
from nonebot_plugin_orm import AsyncSession, get_session
from sqlalchemy import select

from ..exceptions import InvalidBagIndex

from ..models import Bag
from ...nonebot_plugin_item.base.stack import ItemStack


class BagItem:

    def __init__(self, stack: ItemStack, index: int) -> None:
        self.stack = stack
        self.index = index
        self.is_locked = False
    
    async def get_item(self, session: AsyncSession) -> Bag:
        result = await session.scalar(select(Bag).where(
            Bag.user_id == self.stack.user_id,
            Bag.bag_index == self.index
        ))
        if result is None:
            raise InvalidBagIndex()
        return result

    async def setup_bag_lock(self) -> None:
        async with get_session() as session:
            result = await self.get_item(session)
            result.locked = True
            await session.commit()
        self.is_locked = True

    async def save_item(self) -> None:
        async with get_session() as session:
            result = await self.get_item(session)
            result.data = base64.b64encode(json.dumps(self.stack.data).encode())
            result.count = self.stack.count
            await session.commit()

    async def unlock_item(self) -> None:
        async with get_session() as session:
            result = await self.get_item(session)
            result.locked = False
            await session.commit()
        self.is_locked = False

    async def delete(self) -> None:
        if self.is_locked:
            await self.save_item()
        await self.unlock_item()

    def __del__(self) -> None:
        asyncio.create_task(self.delete())