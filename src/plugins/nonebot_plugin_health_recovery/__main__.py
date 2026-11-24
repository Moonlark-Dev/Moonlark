from datetime import datetime, timedelta
from typing import Optional

from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkuser.exceptions import UserNotRegistered
from nonebot_plugin_larkuser.models import UserData
from nonebot_plugin_larkuser.user.base import DOWN_DURATION, DOWN_EXPIRE_HEALTH, MAX_HEALTH
from nonebot_plugin_last_seen.models import LastSeenRecord
from nonebot_plugin_orm import get_session
from sqlalchemy import select

GLOBAL_SESSION_ID = "global"
RECOVERY_AMOUNT = 5

# 定时任务的处理结果，用于统计
RECOVERED = "recovered"
REVIVED = "revived"


async def _get_last_seen_map() -> dict[str, datetime]:
    async with get_session() as session:
        return {
            record.user_id: record.last_seen
            for record in await session.scalars(
                select(LastSeenRecord).where(LastSeenRecord.session_id == GLOBAL_SESSION_ID),
            )
        }


async def _get_candidates(now: datetime, active_threshold: datetime) -> list[tuple[str, Optional[datetime]]]:
    """挑出本次可能需要处理的用户 (user_id, last_seen)。

    只读 user_id / health / downed_at 三列，避免把 config 等字段全部读出来；
    真正是否要写，会在 :func:`_recover_user` 的用户写锁内按数据库最新状态再判断一次。
    """
    last_seen_map = await _get_last_seen_map()
    async with get_session() as session:
        rows = (
            await session.execute(
                select(UserData.user_id, UserData.health, UserData.downed_at).where(
                    UserData.register_time.is_not(None)
                ),
            )
        ).all()
    candidates: list[tuple[str, Optional[datetime]]] = []
    for user_id, health, downed_at in rows:
        last_seen = last_seen_map.get(user_id)
        if health <= 0:
            if downed_at is not None and now - downed_at >= DOWN_DURATION:
                candidates.append((user_id, last_seen))
            continue
        if health < MAX_HEALTH and last_seen is not None and last_seen >= active_threshold:
            candidates.append((user_id, last_seen))
    return candidates


async def _recover_user(
    user_id: str,
    last_seen: Optional[datetime],
    now: datetime,
    active_threshold: datetime,
) -> Optional[str]:
    """在用户写锁内基于数据库最新状态回复 / 复活该用户。

    与其它修改用户数值的操作共用 ``user_write_lock``：锁内重读最新数据行再修改，
    因此不会覆盖同一用户并发发生的扣血 / 治疗 / 救起。
    """
    user = await get_user(user_id, writable=True)

    def _apply(row: UserData) -> Optional[str]:
        if row.health <= 0:
            if row.downed_at is not None and now - row.downed_at >= DOWN_DURATION:
                row.health = DOWN_EXPIRE_HEALTH
                row.downed_at = None
                return REVIVED
            return None
        if last_seen is None or last_seen < active_threshold:
            return None
        if row.health < MAX_HEALTH:
            row.health = min(row.health + RECOVERY_AMOUNT, MAX_HEALTH)
            return RECOVERED
        return None

    return await user.update(_apply)


@scheduler.scheduled_job("interval", hours=1, id="health_recovery_hourly")
async def recover_health() -> None:
    """每小时运行一次：为最近一小时内活跃的已注册未倒地用户回复 5 HP。

    倒地状态已超过 3 小时（DOWN_DURATION）的用户的 HP 也会在此被重置为 1（DOWN_EXPIRE_HEALTH）。

    所有写入都通过 larkuser 的用户写锁完成（与签到、扣血、治疗等共用），
    避免定时任务覆盖同一时刻其它协程对 hp 的修改。
    """
    now = datetime.now()
    active_threshold = now - timedelta(hours=1)
    recovered = 0
    revived = 0
    for user_id, last_seen in await _get_candidates(now, active_threshold):
        try:
            result = await _recover_user(user_id, last_seen, now, active_threshold)
        except UserNotRegistered:
            # 用户在本轮扫描与加锁之间被删除，跳过即可
            continue
        if result == RECOVERED:
            recovered += 1
        elif result == REVIVED:
            revived += 1
    logger.info(f"[health_recovery] 本次恢复 {recovered} 名用户的 HP，复活 {revived} 名倒地用户")
