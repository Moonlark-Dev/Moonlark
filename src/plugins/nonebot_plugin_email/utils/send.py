from datetime import datetime
import json
from typing import Optional
from nonebot.log import logger
from nonebot_plugin_orm import get_scoped_session
from sqlalchemy import select

from ...nonebot_plugin_larkuser.models import UserData
from ..models import EmailData, EmailItem, EmailUser
from ..types import EmailItemData


async def send_email(
    receivers: list[str], subject: str, content: str, author: Optional[str] = None, items: list[EmailItemData] = []
) -> int:
    session = get_scoped_session()
    session.add(email := EmailData(author=author, content=content, subject=subject, time=datetime.now()))
    await session.flush()
    email_id = email.email_id
    for item in items:
        session.add(
            EmailItem(belong=email_id, item_id=item["item_id"], count=item["count"], data=json.dumps(item["data"]))
        )
    for receiver_id in receivers:
        session.add(EmailUser(user_id=receiver_id, email_id=email_id))
    await session.commit()
    logger.info(f"Email {email_id} sent to {receivers}")
    return email_id


async def send_global_email(
    subject: str, content: str, author: Optional[str] = None, items: list[EmailItemData] = []
) -> int:
    session = get_scoped_session()
    receivers = await session.scalars(select(UserData.user_id).where(UserData.register_time.is_not(None)))
    return await send_email(list(receivers.all()), subject, content, author, items)
