import json
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..lang import lang
from ..models import EmailData, EmailItem, EmailUser
from ..types import DictEmailData


async def get_email_data(email_id: int, user_id: str = "-1") -> DictEmailData:
    async with get_session() as session:
        data = await session.get_one(EmailData, email_id)
        user = await session.scalar(select(EmailUser).where(EmailUser.user_id == user_id, EmailUser.email_id == email_id))
        items = await session.scalars(select(EmailItem).where(EmailItem.belong == email_id))
        return {
            "id": data.email_id,
            "author": data.author or await lang.text("email.unknown_author", user_id),
            "content": data.content,
            "subject": data.subject,
            "time": data.time,
            "items": [
                {
                    "item_id": item.item_id,
                    "count": item.count,
                    "data": json.loads(item.data),
                }
                for item in items
            ],
            "is_claimed": user.is_claimed if user else False,
            "is_read": user.is_read if user else False,
        }
