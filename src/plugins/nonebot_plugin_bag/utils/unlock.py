from nonebot import get_driver
from nonebot_plugin_orm import get_session
from sqlalchemy import select
from ..models import Bag
from nonebot.log import logger


@get_driver().on_startup
async def _() -> None:
    count = 0
    async with get_session() as session:
        for item in await session.scalars(select(Bag).where(Bag.locked == True)):
            item.locked = False
            await session.merge(item)
            await session.commit()
            count += 1
    logger.info(f"已解锁 {count} 个物品")
