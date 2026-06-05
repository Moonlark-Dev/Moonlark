"""睡眠控制器

按设计文档实现，不兼容旧代码。
"""

import math
import random
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from nonebot import logger
from nonebot_plugin_apscheduler import scheduler
from ...utils.prompt import get_prompt_text

if TYPE_CHECKING:
    from .moonlark_main import MoonlarkMain

DROWSY_THRESHOLD = 0.8
SLEEP_THRESHOLD = 0.95


class SleepController:

    def __init__(self, moonlark_main: "MoonlarkMain"):
        self.moonlark_main = moonlark_main

        self.sleep_state: bool = False
        self.sleep_begin_time: Optional[datetime] = None
        self.tiredness: float = 0.0
        self.last_message_time: datetime = datetime.now()
        self.last_reply_time: datetime = datetime.now()
        self.consecutive_replies: int = 0
        self.sleep_think_count: int = 0  # 睡眠后定时决策计数器
        self.context_cleared: bool = False  # 是否已清除过上下文

        # 定时器：每10分钟检查困倦度（清醒时）或睡眠决策检查（睡眠时）
        scheduler.scheduled_job("interval", minutes=10, id="sleep_controller_process_timer")(self.process_timer)

    # ========================================================================
    # 困倦度计算
    # ========================================================================

    @staticmethod
    def circadian(hour: float) -> float:
        return 0.5 + 0.3 * math.cos(2 * math.pi * (hour - 4) / 24) + 0.1 * math.cos(2 * math.pi * (hour - 14) / 12)

    @staticmethod
    def silence_factor(minutes_since_last_msg: float) -> float:
        return min(1.0, minutes_since_last_msg / 45.0)

    @staticmethod
    def fatigue_factor(consecutive_replies: int) -> float:
        return min(1.0, consecutive_replies / 15.0)

    @staticmethod
    def gating(circadian: float) -> float:
        return max(0.0, min(1.0, (circadian - 0.4) / 0.4))

    def calculate_sleepiness_index(self) -> float:
        now = datetime.now()
        hour = now.hour + now.minute / 60.0
        minutes_since_last = (now - self.last_message_time).total_seconds() / 60.0

        b = self.circadian(hour)
        s = self.silence_factor(minutes_since_last)
        f = self.fatigue_factor(self.consecutive_replies)
        g = self.gating(b)
        epsilon = random.uniform(-0.05, 0.05)

        self.tiredness = max(0.0, min(1.0, 0.50 * b + 0.30 * s + 0.20 * f * g + epsilon))

        logger.debug(
            f"[SleepController] hour={hour:.1f} B={b:.3f} S={s:.3f} "
            f"F={f:.3f} G={g:.3f} ε={epsilon:.3f} → tiredness={self.tiredness:.3f}"
        )
        return self.tiredness

    # ========================================================================
    # 核心方法
    # ========================================================================

    async def request_think(self) -> None:
        """睡眠状态下的定时决策（每10分钟由 process_timer 调用）

        内部处理 wake_up，不返回值。
        入睡后首次决策继续睡时（入睡到决策 >20分钟），重置所有会话上下文。
        """
        from nonebot_plugin_openai.utils.chat import fetch_json
        from nonebot_plugin_openai.utils.message import generate_message
        from ...lang import lang
        from ...models import SleepThinkResponse

        self.sleep_think_count += 1
        now = datetime.now()
        sleep_duration = 0
        if self.sleep_begin_time:
            sleep_duration = (now - self.sleep_begin_time).total_seconds() / 60

        try:
            identity_prompt = await get_prompt_text("identity")
            summary = self.moonlark_main.state.get("instant_memory_summary", "暂无群聊记忆。")

            system_prompt = await lang.text(
                "moonlark_main.sleep_think.system",
                self.moonlark_main.lang_str,
                now.strftime("%Y-%m-%d %H:%M:%S"),
                str(int(sleep_duration)),
                identity_prompt,
                summary,
            )
            user_prompt = await lang.text(
                "moonlark_main.sleep_think.user",
                self.moonlark_main.lang_str,
            )

            result = await fetch_json(
                [generate_message(system_prompt, "system"), generate_message(user_prompt, "user")],
                SleepThinkResponse,
                identify="SleepController - Sleep Think",
                reasoning_effort="low",
            )

            if result.sleep_decision == "wake_up":
                await self.wake_up()
                self.moonlark_main._update_decision_history("wake_up")
            else:
                # 决定继续睡：检查是否需要清除上下文
                await self._maybe_clear_context(sleep_duration)

        except Exception as e:
            logger.exception(f"[SleepController] 睡眠决策失败: {e}")

    async def _maybe_clear_context(self, sleep_duration: float) -> None:
        """入睡后首次决策继续睡时，重置所有会话的消息队列上下文。

        条件：入睡到决策时间 > 30 分钟，且未清除过。
        """
        if self.context_cleared:
            return

        if sleep_duration < 30:
            logger.info(f"[SleepController] 入睡 {int(sleep_duration)} 分钟，不足30分钟，暂不重置上下文")
            return

        # 满足条件，重置所有会话的消息队列上下文
        logger.info("[SleepController] 入睡后首次继续睡决策，重置所有会话消息队列上下文")
        await self._reset_all_message_queues()
        self.context_cleared = True

    async def _reset_all_message_queues(self) -> None:
        """重置所有会话的消息队列（内存 + 数据库），但不销毁 session 对象"""
        from ..session import groups

        for session_id, session in list(groups.items()):
            try:
                await session.processor.openai_messages._reset_and_clear_db(session_id)
                logger.info(f"[SleepController] 已重置会话消息队列: {session_id}")
            except Exception as e:
                logger.exception(f"[SleepController] 重置会话 {session_id} 消息队列失败: {e}")

    async def handle_mention(self, chat_context: list) -> bool:
        """当被提及时调用。返回 True 表示已唤醒，应正常回复。

        内部处理 wake_up 和状态更新。
        """
        from nonebot_plugin_openai.utils.chat import fetch_message
        from nonebot_plugin_openai.utils.message import generate_message
        from ...lang import lang

        context_text = "\n".join(chat_context[-5:]) if chat_context else ""

        try:
            identity_prompt = await get_prompt_text("identity")
            summary = self.moonlark_main.state.get("instant_memory_summary", "暂无群聊记忆。")

            system_prompt = await lang.text(
                "moonlark_main.mention.system",
                self.moonlark_main.lang_str,
                identity_prompt,
                summary,
            )
            user_prompt = await lang.text(
                "moonlark_main.mention.user",
                self.moonlark_main.lang_str,
                context_text,
            )

            response = await fetch_message(
                [generate_message(system_prompt, "system"), generate_message(user_prompt, "user")],
                identify="SleepController - Handle Mention",
                reasoning_effort="low",
            )
            should_wake = response.strip().lower() == "wake_up"

            if should_wake:
                await self.wake_up()
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
        """困倦度达标，进入睡眠"""
        self.sleep_state = True
        self.sleep_begin_time = datetime.now()
        self.moonlark_main.state["sleep_mode"] = True
        self.moonlark_main.action_decider.reset()
        logger.info("[SleepController] 进入睡眠模式，已重置 ActionDecider")

    async def sleep(self) -> None:
        """睡觉工具调用"""
        await self.handle_tired()

    async def process_timer(self) -> None:
        """定时回调（每10分钟）。

        清醒时：检查困倦度，如果达标则触发睡眠。
        睡眠时：调用 request_think 做定时决策检查（是否该醒来/清除上下文）。
        """
        if self.sleep_state:
            await self.request_think()
            return

        tiredness = self.calculate_sleepiness_index()
        if tiredness >= SLEEP_THRESHOLD:
            logger.info(f"[SleepController] 困倦度 {tiredness:.3f} >= {SLEEP_THRESHOLD}，触发睡眠")
            await self.handle_tired()

    async def handle_decision(self, sleep_decision: str) -> None:
        """处理来自 MoonlarkMain 的 sleep_decision 决策"""
        if sleep_decision == "go_to_sleep":
            await self.handle_tired()
        elif sleep_decision == "wake_up" and self.moonlark_main.state["sleep_mode"]:
            await self.wake_up()

    async def submit_sleep_decision(self, deal_type: str, delay_minutes: int = 5, reason: str = "") -> str:
        """处理来自子会话的睡眠决策"""
        if deal_type == "ready":
            await self.handle_tired()
            return "已进入睡眠模式。"
        else:
            delay = min(delay_minutes, 30)
            return f"已延迟 {delay} 分钟睡觉。" + (f"原因: {reason}" if reason else "")

    async def wake_up(self) -> None:
        self.sleep_state = False
        self.sleep_begin_time = None
        self.tiredness = 0.0
        self.consecutive_replies = 0
        self.sleep_think_count = 0
        self.context_cleared = False
        self.moonlark_main.state["sleep_mode"] = False
        # 重置 ActionDecider 以便下次从干净状态启动
        self.moonlark_main.action_decider.reset()
        logger.info("[SleepController] 已唤醒")
