
import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal, Optional

from nonebot import logger
from nonebot_plugin_apscheduler import scheduler

from nonebot_plugin_chat.core.session import groups
from nonebot_plugin_chat.utils.instant_mem import delete_sleep_memory, post_instant_memory
from nonebot_plugin_openai.utils.chat import fetch_message, generate_message

if TYPE_CHECKING:
    from .main_session import MainSession


from ...utils.prompt import get_prompt_text
from ...lang import lang

class SleepController:
    """控制与睡眠决策相关的所有功能"""

    def __init__(self, main_session: "MainSession"):
        self.main_session = main_session
        self.pending_sleep_decisions: dict[str, dict] = {}
        scheduler.scheduled_job("cron", hour=8, minute=30)(self.generate_sleep_time)

    async def generate_sleep_time(self) -> None:
        """每天8:30执行的定时任务，决定今天的睡觉时间"""
        # 生成睡觉时间决策的prompt
        system_prompt = await lang.text(
            "main_session.sleep_time_prompt.system",
            self.main_session.lang_str,
            await get_prompt_text("identity"),
            await self.main_session.get_additional_prompt(),
            await self.main_session.get_recent_actions_text(self.main_session.lang_str),
        )
        user_prompt = await lang.text("main_session.sleep_time_prompt.user", self.main_session.lang_str)

        try:
            messages = [
                generate_message(system_prompt, "system"),
                generate_message(user_prompt, "user"),
            ]
            response = await fetch_message(messages, identify="Sleep Time Decision")
            # 解析返回的时间（格式：HH:MM）
            time_str = response.strip()
            if ":" in time_str:
                hour, minute = map(int, time_str.split(":"))
                now = datetime.now()
                scheduled_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if scheduled_time < now:
                    return

                # 写入instant_mem
                await post_instant_memory(
                    category="myself",
                    content=f"你在决定于 {time_str} 睡觉。",
                    keywords=["睡觉", "睡眠", "休息"],
                    expire_level=4,
                    lang_str=self.main_session.lang_str,
                    ctx_id="main_",
                    name="main_session",
                )

                scheduler.add_job(
                    self.ask_sleep,
                    "date",
                    run_date=scheduled_time,
                )
        except Exception as e:
            logger.exception(e)

    async def ask_sleep(self) -> None:
        """询问是否可以睡觉"""

        dt = datetime.now()
        # 开始决策流程
        self.pending_sleep_decisions = {}
        # 找出最近5分钟有活动的session
        active_sessions = []
        for session_id, group in groups.items():
            if group.cached_messages and (dt - group.cached_messages[-1]["send_time"]) < timedelta(minutes=5):
                active_sessions.append(group)
        # 向这些session发送睡觉提示
        sleep_prompt = await lang.text("main_session.sleep_prompt", self.main_session.lang_str)
        for session in active_sessions:
            await session.add_event(sleep_prompt, "all")
        # 启动决策收集任务
        asyncio.create_task(self.collect_sleep_decisions())

    async def collect_sleep_decisions(self) -> None:
        """收集所有session的睡觉决策并处理"""
        from nonebot_plugin_chat.lang import lang

        # 等待1.5分钟收集决策
        sleep_time = datetime.now()
        await asyncio.sleep(90)
        # 检查是否有delay
        delay_decisions = [
            (sid, dec) for sid, dec in self.pending_sleep_decisions.items() if dec["deal_type"] == "delay"
        ]
        if delay_decisions:
            # 计算平均延迟时间
            avg_delay = sum(dec["delay_minutes"] for _, dec in delay_decisions) / len(delay_decisions)
            # 拼接非空原因
            reasons = [dec["reason"] for _, dec in delay_decisions if dec["reason"]]
            reason_text = "、".join(reasons) if reasons else ""

            # 更新睡觉时间
            new_sleep_time = sleep_time + timedelta(minutes=avg_delay)
            scheduler.add_job(self.ask_sleep, "date", run_date=new_sleep_time)

            # 向所有调用了工具的session推送结果
            result_text = await lang.text(
                "main_session.sleep_decision.delay", self.main_session.lang_str, reason_text, new_sleep_time.strftime("%H:%M")
            )
            for session_id, decision in self.pending_sleep_decisions.items():
                if session_id in groups:
                    # 设置Future结果
                    if "future" in decision and not decision["future"].done():
                        decision["future"].set_result(result_text)
                    else:
                        await groups[session_id].add_event(result_text, "all")
        else:
            # 全部ready，5分钟后睡觉
            result_text = await lang.text("main_session.sleep_decision.ready", self.main_session.lang_str)
            for session_id, decision in self.pending_sleep_decisions.items():
                if session_id in groups:
                    # 设置Future结果
                    if "future" in decision and not decision["future"].done():
                        decision["future"].set_result(result_text)
                    else:
                        await groups[session_id].add_event(result_text, "all")

            await asyncio.sleep(300)
            await self.main_session.request_think("ready_sleep", None)

        # 清理决策状态
        self.pending_sleep_decisions = {}
        # 删除instant_mem中关于睡觉的记忆
        delete_sleep_memory()

    async def submit_sleep_decision(
        self,
        session_id: str,
        deal_type: Literal["ready", "delay"],
        delay_minutes: Optional[int] = None,
        reason: Optional[str] = None,
        future: Optional[asyncio.Future] = None,
    ) -> None:
        """提交睡觉决策"""
        if session_id in self.pending_sleep_decisions:
            return  # 已经提交过

        self.pending_sleep_decisions[session_id] = {
            "deal_type": deal_type,
            "delay_minutes": delay_minutes or 0,
            "reason": reason or "",
        }
        if future:
            self.pending_sleep_decisions[session_id]["future"] = future
