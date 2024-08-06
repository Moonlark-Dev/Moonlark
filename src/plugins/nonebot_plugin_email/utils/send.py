from datetime import datetime
from src.plugins.nonebot_plugin_larkutils import get_main_account
import json
from typing import Optional
from nonebot.log import logger
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ...nonebot_plugin_larkuser.models import UserData
from ..models import EmailData, EmailItem, EmailUser
from ..types import EmailItemData


async def send_email(
    receivers: list[str], subject: str, content: str, author: Optional[str] = None, items: list[EmailItemData] = []
) -> int:
    session = get_session()
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
    await session.close()
    logger.info(f"Email {email_id} sent to {receivers}")
    return email_id


async def send_global_email(
    subject: str, content: str, author: Optional[str] = None, items: list[EmailItemData] = []
) -> int:
    async with get_session() as session:
        receivers = list((await session.scalars(
            select(UserData.user_id).where(UserData.register_time.is_not(None)))).all())
        for i in range(len(receivers)):
            receivers[i] = await get_main_account(receivers[i])
        receivers = list(set(receivers))
        return await send_email(receivers, subject, content, author, items)
