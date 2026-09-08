from datetime import datetime, timedelta

from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_larkuser.models import UserData
from nonebot_plugin_larkuser.user.base import DOWN_DURATION, MAX_HEALTH, REVIVE_HEALTH
from nonebot_plugin_last_seen.models import LastSeenRecord
from nonebot_plugin_orm import get_session
from sqlalchemy import select

GLOBAL_SESSION_ID = "global"
RECOVERY_AMOUNT = 5


@scheduler.scheduled_job("interval", hours=1, id="health_recovery_hourly")
async def recover_health() -> None:
    """每小时运行一次：为最近一小时内活跃的已注册未倒地用户回复 5 HP。

    倒地状态已超过 30 分钟的用户的 HP 也会在此被重置为 5。
    """
    now = datetime.now()
    active_threshold = now - timedelta(hours=1)
    recovered = 0
    revived = 0
    async with get_session() as session:
        last_seen_map = {
            record.user_id: record.last_seen
            for record in await session.scalars(
                select(LastSeenRecord).where(LastSeenRecord.session_id == GLOBAL_SESSION_ID),
            )
        }
        users = (await session.scalars(select(UserData).where(UserData.register_time.is_not(None)))).all()
        for user in users:
            if user.health <= 0:
                if user.downed_at is not None and now - user.downed_at >= DOWN_DURATION:
                    user.health = REVIVE_HEALTH
                    user.downed_at = None
                    revived += 1
                continue
            last_seen = last_seen_map.get(user.user_id)
            if last_seen is None or last_seen < active_threshold:
                continue
            if user.health < MAX_HEALTH:
                user.health = min(user.health + RECOVERY_AMOUNT, MAX_HEALTH)
                recovered += 1
        await session.commit()
    logger.info(f"[health_recovery] 本次恢复 {recovered} 名用户的 HP，复活 {revived} 名倒地用户")
