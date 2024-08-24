from datetime import datetime, timedelta
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .remove import remove_email
from ..models import EmailData
from ..config import config


@scheduler.scheduled_job("cron", day="*", id="remove_expired_email")
async def _() -> None:
    session = get_session()
    t = datetime.now() - timedelta(days=config.email_expired_days)
    result = await session.scalars(select(EmailData).where(EmailData.time < t))
    for email in result:
        await remove_email(email.email_id)
    await session.close()
