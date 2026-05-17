import random
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from nonebot import logger
from nonebot_plugin_apscheduler import scheduler

from nonebot_plugin_chat.core.session import groups

if TYPE_CHECKING:
    from .main_session import MainSession

from ...lang import lang

EXPECTED_AWAKE_HOURS = 16
MIN_AWAKE_HOURS = 14
MAX_AWAKE_HOURS = 18
RANDOM_MINUTES_RANGE = 30


class SleepController:
    """控制与睡眠相关的所有功能"""

    def __init__(self, main_session: "MainSession"):
        self.main_session = main_session
        now = datetime.now()
        self.last_wake_up_time: datetime = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if self.last_wake_up_time > now:
            self.last_wake_up_time -= timedelta(days=1)
        self._drowsy_job_id: Optional[str] = None
        self._schedule_drowsy()

    def on_wake_up(self) -> None:
        """记录起床时间并安排下一次犯困时间"""
        self.last_wake_up_time = datetime.now()
        self._schedule_drowsy()

    def _calculate_drowsy_time(self, wake_up_time: datetime) -> datetime:
        """根据起床时间计算犯困时间"""
        base_drowsy = wake_up_time + timedelta(hours=EXPECTED_AWAKE_HOURS)
        random_offset = random.randint(-RANDOM_MINUTES_RANGE, RANDOM_MINUTES_RANGE)
        drowsy_time = base_drowsy + timedelta(minutes=random_offset)
        lower_bound = wake_up_time + timedelta(hours=MIN_AWAKE_HOURS)
        upper_bound = wake_up_time + timedelta(hours=MAX_AWAKE_HOURS)
        if drowsy_time < lower_bound:
            drowsy_time = lower_bound
        elif drowsy_time > upper_bound:
            drowsy_time = upper_bound
        return drowsy_time

    def _schedule_drowsy(self) -> None:
        """安排犯困事件的定时任务"""
        if self._drowsy_job_id:
            try:
                scheduler.remove_job(self._drowsy_job_id)
            except Exception:
                pass
            self._drowsy_job_id = None

        drowsy_time = self._calculate_drowsy_time(self.last_wake_up_time)
        now = datetime.now()
        if drowsy_time <= now:
            logger.warning(f"[SleepController] 计算的犯困时间 {drowsy_time} 已过，跳过")
            return

        job = scheduler.add_job(
            self._push_drowsy_event,
            "date",
            run_date=drowsy_time,
        )
        self._drowsy_job_id = job.id
        logger.info(
            f"[SleepController] 起床时间: {self.last_wake_up_time.strftime('%H:%M')}, "
            f"犯困时间: {drowsy_time.strftime('%H:%M')}"
        )

    async def _push_drowsy_event(self) -> None:
        """向所有会话推送犯困事件"""
        self._drowsy_job_id = None
        drowsy_prompt = await lang.text("sleep.drowsy_prompt", self.main_session.lang_str)
        for session in groups.values():
            await session.add_event(drowsy_prompt, "none")
        logger.info("[SleepController] 已向所有会话推送犯困事件")
