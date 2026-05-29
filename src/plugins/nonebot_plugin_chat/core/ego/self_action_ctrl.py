"""自主活动控制器

按设计文档实现：
- 管理当前正在进行的自主活动（如"学习CSS"、"做拉伸"）
- 提供活动计时和自动结束功能
- 维护活动历史记录
- duration 由单独请求 LLM 生成
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from nonebot import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_openai.utils.chat import fetch_json
from nonebot_plugin_openai.utils.message import generate_message
from ...lang import lang
from ...models import SelfActionDurationResponse

if TYPE_CHECKING:
    from .moonlark_main import MoonlarkMain


class SelfActionController:
    """自主活动控制器

    按设计文档属性：
    - current_activity: Optional[str]
    - activity_start_time: Optional[datetime]
    - activity_duration: int (秒，0=无限)
    - activity_history: list
    """

    def __init__(self, moonlark_main: "MoonlarkMain") -> None:
        self.moonlark_main = moonlark_main
        self.current_activity: Optional[str] = None
        self.activity_start_time: Optional[datetime] = None
        self.activity_duration: int = 0
        self.activity_history: list[dict] = []

        # 注册定时器，每分钟检查活动超时
        scheduler.scheduled_job("interval", minutes=1, id="self_action_tick")(self.tick)

    async def start_activity(self, activity: str, duration_seconds: int = 0) -> None:
        """开始一项新活动

        按设计文档：
        1. 若已有活动在进行，打断并记录
        2. 若未提供 duration，调用 LLM 生成
        3. 记录开始时间和持续时间

        Args:
            activity: 活动描述（如"学习CSS"、"做拉伸"）
            duration_seconds: 计划持续时间（秒），0 表示由 LLM 生成
        """
        # 若已有活动在进行，打断并记录
        if self.current_activity:
            logger.info(f"[SelfAction] 打断当前活动: {self.current_activity}")
            await self.finish_activity(completed=False)

        # 若未提供 duration，调用 LLM 生成
        if duration_seconds <= 0:
            duration_seconds = await self._generate_duration(activity)

        self.current_activity = activity
        self.activity_start_time = datetime.now()
        self.activity_duration = duration_seconds

        logger.info(f"[SelfAction] 开始活动: {activity}，计划时长: {duration_seconds}秒")

    async def _generate_duration(self, activity: str) -> int:
        """调用 LLM 生成活动持续时间（秒）

        Args:
            activity: 活动描述

        Returns:
            持续时间（秒），默认 300 秒（5分钟）
        """
        try:
            system_prompt = await lang.text(
                "self_action.duration.system",
                self.moonlark_main.lang_str,
            )
            user_prompt = await lang.text(
                "self_action.duration.user",
                self.moonlark_main.lang_str,
                activity,
            )

            result = await fetch_json(
                [
                    generate_message(system_prompt, "system"),
                    generate_message(user_prompt, "user"),
                ],
                SelfActionDurationResponse,
                identify="SelfAction - Generate Duration",
                reasoning_effort="low",
            )

            return max(60, min(3600, result.duration_minutes * 60))

        except Exception as e:
            logger.exception(f"[SelfAction] 生成 duration 失败: {e}")
            return 300  # 默认 5分钟

    async def tick(self) -> None:
        """检查当前活动是否超时，由定时器每分钟调用"""
        if not self.current_activity or self.activity_duration == 0:
            return

        elapsed = (datetime.now() - self.activity_start_time).total_seconds()
        if elapsed >= self.activity_duration:
            logger.info(f"[SelfAction] 活动超时完成: {self.current_activity}")
            await self.finish_activity(completed=True)

    async def finish_activity(self, completed: bool = True) -> None:
        """结束当前活动

        Args:
            completed: True 表示正常完成，False 表示被打断
        """
        if not self.current_activity:
            return

        end_time = datetime.now()
        elapsed = (end_time - self.activity_start_time).total_seconds()

        # 记录到历史
        self.activity_history.append({
            "activity": self.current_activity,
            "start_time": self.activity_start_time,
            "end_time": end_time,
            "duration": elapsed,
            "completed": completed,
        })
        # 只保留最近 20 条
        self.activity_history = self.activity_history[-20:]

        activity_name = self.current_activity
        self.current_activity = None
        self.activity_start_time = None
        self.activity_duration = 0

        if completed:
            # 通知 MoonlarkMain 活动完成，触发新一轮决策
            logger.info(f"[SelfAction] 活动完成: {activity_name}，触发决策")
            await self.moonlark_main.request_think("task_finished", activity_name)

    def get_status_text(self) -> str:
        """返回当前活动状态文本，供 MoonlarkMain 的 Prompt 使用"""
        if not self.current_activity:
            return "当前无自主活动"

        elapsed = (datetime.now() - self.activity_start_time).total_seconds()
        if self.activity_duration > 0:
            remaining = max(0, self.activity_duration - elapsed)
            return (
                f"正在{self.current_activity}，"
                f"已进行 {int(elapsed) // 60} 分钟，"
                f"剩余 {int(remaining) // 60} 分钟"
            )
        else:
            return f"正在{self.current_activity}，已进行 {int(elapsed) // 60} 分钟"

    def get_recent_activities(self, limit: int = 5) -> list[dict]:
        """获取最近完成的活动"""
        return self.activity_history[-limit:]

    def get_activity_remaining(self) -> int:
        """获取当前活动剩余秒数"""
        if not self.current_activity or not self.activity_start_time:
            return 0
        if self.activity_duration == 0:
            return -1  # 无限
        elapsed = (datetime.now() - self.activity_start_time).total_seconds()
        return max(0, int(self.activity_duration - elapsed))
