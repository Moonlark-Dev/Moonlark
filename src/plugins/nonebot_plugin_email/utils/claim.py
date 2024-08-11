import json
from sqlalchemy import select
from nonebot_plugin_orm import get_session
from nonebot.log import logger
from .read import mark_email_read
from ...nonebot_plugin_bag.utils.give import give_item_by_list
from ...nonebot_plugin_item.utils.string import get_location_by_id
from ...nonebot_plugin_item.utils.get import get_item
from ..models import EmailItem
from ...nonebot_plugin_item.base.stack import ItemStack

"""
async def claim_email(email_id: int, user_id: str) -> list[ItemStack]:
    logger.debug(str(email_id))
    item_list = []
    async with get_session() as session:
        for item in await session.scalars(select(EmailItem).where(EmailItem.belong == email_id)):
            item_list.append(
                await get_item(get_location_by_id(item.item_id), user_id, item.count, json.loads(item.data))
            )
            logger.debug("Now item list: {item_list}")
            await give_item(user_id, item_list[-1])
    await mark_email_read(email_id, user_id, True)
    return item_list
"""


async def claim_email(email_id: int, user_id: str) -> list[ItemStack]:
    logger.debug(str(email_id))
    item_list = []
    async with get_session() as session:
        items = await session.scalars(select(EmailItem).where(EmailItem.belong == email_id))
        for item in items:
            item_list.append(
                await get_item(get_location_by_id(item.item_id), user_id, item.count, json.loads(item.data))
            )
            item_data = {"item_id": item.item_id, "count": item.count, "data": json.loads(item.data)}
            logger.debug(f"{item_data=}")
            await give_item_by_list(user_id, [item_data])
            logger.debug(f"Now item list: {item_list}")
    # await mark_email_read(email_id, user_id, True)
    return item_list
