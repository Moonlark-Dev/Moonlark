"""睡眠控制器

睡眠/清醒二状态机，困倦度公式（经验证）：
  B = 0.279 + 0.544 * cos(2π * (hour - 2.5) / 24)
  tiredness = max(0, min(1, B + 0.50*S + 0.50*F))

无疲劳时：00:30 达到 SLEEP_THRESHOLD(0.75)，08:00 达到 WAKE_THRESHOLD(0.35)
有疲劳时：12:30(F=1,S=1)达到 SLEEP_THRESHOLD，14:30 恢复到 < WAKE_THRESHOLD
"""

import asyncio
import math
import random
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from nonebot import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_openai.utils.message import get_messages

if TYPE_CHECKING:
    from .moonlark_main import MoonlarkMain

SLEEP_THRESHOLD = 0.75
WAKE_THRESHOLD = 0.35


class SleepController:
    def __init__(self, moonlark_main: "MoonlarkMain"):
        self.moonlark_main = moonlark_main

        self.sleep_state: bool = False
        self.sleep_begin_time: Optional[datetime] = None
        self.tiredness: float = 0.0
        self.last_message_time: datetime = datetime.now()
        self.last_reply_time: datetime = datetime.now()
        self.consecutive_replies: int = 0
        self._sleep_tasks: set[asyncio.Task] = set()
        self._pending_sleep_tasks: set[asyncio.Task] = set()

        scheduler.scheduled_job("interval", minutes=10, id="sleep_controller_process_timer")(self.process_timer)

    @staticmethod
    def circadian(hour: float) -> float:
        return 0.279 + 0.544 * math.cos(2 * math.pi * (hour - 2.5) / 24)

    @staticmethod
    def silence_factor(minutes_since_last_msg: float) -> float:
        return min(1.0, minutes_since_last_msg / 30.0)

    @staticmethod
    def fatigue_factor(consecutive_replies: int) -> float:
        return min(1.0, consecutive_replies / 20.0)

    def calculate_sleepiness_index(self) -> float:
        now = datetime.now()
        hour = now.hour + now.minute / 60.0
        minutes_since_last = (now - self.last_message_time).total_seconds() / 60.0

        b = self.circadian(hour)
        s = self.silence_factor(minutes_since_last)
        f = self.fatigue_factor(self.consecutive_replies)
        epsilon = random.uniform(-0.02, 0.02)

        self.tiredness = max(0.0, min(1.0, b + 0.50 * s + 0.50 * f + epsilon))

        logger.debug(
            f"[SleepController] hour={hour:.1f} B={b:.3f} S={s:.3f} "
            f"F={f:.3f} ε={epsilon:.4f} → tiredness={self.tiredness:.4f}",
        )
        return self.tiredness

    async def handle_mention(
        self, chat_context: list, session_name: str = "", nickname: str = "", session_id: str = ""
    ) -> bool:
        context_text = "\n".join(chat_context[-5:]) if chat_context else ""

        try:
            messages = await get_messages(
                "mention",
                tiredness=str(round(self.tiredness, 2)),
                context=context_text,
            )

            response = await fetch_message(
                messages,
                identify="SleepController - Handle Mention",
                reasoning_effort="low",
            )
            should_wake = response.strip().lower() == "wake_up"

            if should_wake:
                reason = "被提及"
                if session_name or nickname:
                    parts = []
                    if session_name:
                        parts.append(f"会话: {session_name}")
                    if nickname:
                        parts.append(f"用户: {nickname}")
                    reason += f" ({', '.join(parts)})"
                await self.wake_up(reason, exclude_session_id=session_id)
                return True
            return False

        except Exception as e:
            logger.exception(f"[SleepController] mention 判断失败: {e}")
            return False

    def handle_message(self) -> None:
        self.last_message_time = datetime.now()
        self.calculate_sleepiness_index()

    def handle_reply(self) -> None:
        self.last_reply_time = datetime.now()
        self.consecutive_replies += 1
        self.calculate_sleepiness_index()

    async def handle_tired(self) -> None:
        self.sleep_state = True
        self.sleep_begin_time = datetime.now()
        self.moonlark_main.state["sleep_mode"] = True
        self.moonlark_main.state["injected_note_ids"] = []
        logger.info("[SleepController] 进入睡眠模式")

    async def sleep(self) -> None:
        await self.handle_tired()

    async def process_timer(self) -> None:
        if self.sleep_state:
            # 睡眠中：由困倦度曲线决定唤醒（不再定时询问 LLM）
            now = datetime.now()
            hour = now.hour + now.minute / 60.0
            curve = self.circadian(hour)
            if curve < WAKE_THRESHOLD:
                logger.info(f"[SleepController] 困倦度曲线 {curve:.3f} < {WAKE_THRESHOLD}，自然唤醒")
                await self.wake_up("困倦度曲线降至唤醒阈值以下")
            return

        tiredness = self.calculate_sleepiness_index()
        if tiredness >= SLEEP_THRESHOLD:
            logger.info(f"[SleepController] 困倦度 {tiredness:.3f} >= {SLEEP_THRESHOLD}，触发睡眠")
            await self.handle_tired()

    async def submit_sleep_decision(self, deal_type: str, delay_minutes: int = 5, reason: str = "") -> str:
        if deal_type == "ready":
            await self.handle_tired()
            return "已进入睡眠模式。"
        delay = min(delay_minutes, 30)
        if delay <= 0:
            await self.handle_tired()
            return "已进入睡眠模式。"
        # 真正的延迟入睡：倒计时结束后自动进入睡眠
        task = asyncio.create_task(self._delayed_sleep(delay))
        self._pending_sleep_tasks.add(task)
        task.add_done_callback(self._pending_sleep_tasks.discard)
        return f"已延迟 {delay} 分钟睡觉。" + (f"原因: {reason}" if reason else "")

    async def _delayed_sleep(self, delay_minutes: int) -> None:
        """延迟入睡：倒计时结束后进入睡眠（若期间已入睡则跳过）"""
        await asyncio.sleep(delay_minutes * 60)
        if self.sleep_state:
            logger.info("[SleepController] 延迟入睡触发时已在睡眠中，跳过")
            return
        logger.info(f"[SleepController] 延迟 {delay_minutes} 分钟结束，进入睡眠")
        await self.handle_tired()

    async def wake_up(self, reason: str = "", exclude_session_id: str = "") -> None:
        # 唤醒时取消未触发的延迟入睡任务
        for task in list(self._pending_sleep_tasks):
            task.cancel()
        self._pending_sleep_tasks.clear()
        self.sleep_state = False
        self.sleep_begin_time = None
        self.tiredness = 0.0
        self.consecutive_replies = 0
        self.moonlark_main.state["sleep_mode"] = False
        if reason:
            logger.info(f"[SleepController] 已唤醒, 原因: {reason}")
        else:
            logger.info("[SleepController] 已唤醒")
        # 唤醒后重置各会话上下文，视为新一轮会话创建（重新生成会话信息）
        # 排除正在处理唤醒的会话，避免清空触发唤醒的上下文
        await self._reset_all_sessions(exclude_session_id=exclude_session_id)

    async def _reset_all_sessions(self, exclude_session_id: str = "") -> None:
        """重置所有活动会话的消息队列（内存 + 数据库），可排除指定会话"""
        from ..session import groups

        for session_id, session in groups.items():
            if session_id == exclude_session_id:
                continue
            try:
                await session.processor.openai_messages._reset_and_clear_db(session_id)
                logger.info(f"[SleepController] 唤醒后已重置会话 {session_id} 的上下文")
            except Exception as e:
                logger.warning(f"[SleepController] 唤醒后重置会话 {session_id} 失败: {e}")
