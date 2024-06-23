import json
from sqlalchemy import select
from nonebot_plugin_orm import get_session

from .read import mark_email_read
from ...nonebot_plugin_bag.utils.bag import give_item
from ...nonebot_plugin_item.utils.string import get_location_by_id
from ...nonebot_plugin_item.utils.get import get_item
from ..models import EmailItem
from ...nonebot_plugin_item.base.stack import ItemStack


async def claim_email(email_id: int, user_id: str) -> list[ItemStack]:
    item_list = []
    async with get_session() as session:
        for item in await session.scalars(select(EmailItem).where(EmailItem.belong == email_id)):
            item_list.append(
                await get_item(get_location_by_id(item.item_id), user_id, item.count, json.loads(item.data))
            )
            await give_item(user_id, item_list[-1])
    await mark_email_read(email_id, user_id, True)
    return item_list
