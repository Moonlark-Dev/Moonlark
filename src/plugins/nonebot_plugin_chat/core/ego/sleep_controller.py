"""睡眠控制器

按设计文档实现，不兼容旧代码。
"""

import math
import random
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from nonebot import logger
from nonebot_plugin_apscheduler import scheduler

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

        # 定时器：清醒时每10分钟检查困倦度
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
        """睡眠状态下的定时决策（每30分钟由 MoonlarkMain 调用）

        内部处理 wake_up，不返回值。
        """
        from nonebot_plugin_openai.utils.chat import fetch_json
        from nonebot_plugin_openai.utils.message import generate_message
        from ...lang import lang
        from ...models import SleepThinkResponse

        now = datetime.now()
        sleep_duration = 0
        if self.sleep_begin_time:
            sleep_duration = (now - self.sleep_begin_time).total_seconds() / 60

        try:
            system_prompt = await lang.text(
                "moonlark_main.sleep_think.system",
                self.moonlark_main.lang_str,
                now.strftime("%Y-%m-%d %H:%M:%S"),
                str(int(sleep_duration)),
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

        except Exception as e:
            logger.exception(f"[SleepController] 睡眠决策失败: {e}")

    async def handle_mention(self, chat_context: list) -> bool:
        """当被提及时调用。返回 True 表示已唤醒，应正常回复。

        内部处理 wake_up 和状态更新。
        """
        from nonebot_plugin_openai.utils.chat import fetch_message
        from nonebot_plugin_openai.utils.message import generate_message
        from ...lang import lang

        context_text = "\n".join(chat_context[-5:]) if chat_context else ""

        try:
            system_prompt = await lang.text(
                "moonlark_main.mention.system",
                self.moonlark_main.lang_str,
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
        logger.info("[SleepController] 进入睡眠模式")

    async def process_timer(self) -> None:
        """定时检查困倦度（自己的定时器，每10分钟）"""
        if self.sleep_state:
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
        self.moonlark_main.state["sleep_mode"] = False
        logger.info("[SleepController] 已唤醒")
