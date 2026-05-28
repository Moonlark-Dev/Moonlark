"""睡眠控制器

按设计文档实现：
- 管理睡眠状态（sleep_state、sleep_begin_time）
- 计算困倦度（calculate_sleepiness_index）
- 处理睡眠时的定时决策和 mention 唤醒
- handle_message / handle_reply 更新时间
- handle_tired 触发睡眠
- process_timer 定时检查困倦度
"""

import math
import random
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from nonebot import logger

if TYPE_CHECKING:
    from .moonlark_main import MoonlarkMain

DROWSY_THRESHOLD = 0.8
SLEEP_THRESHOLD = 0.95


class SleepController:
    """睡眠控制器

    按设计文档属性：
    - sleep_state: bool
    - sleep_begin_time: Optional[datetime]
    - tiredness: float (0..1)
    - last_message_time: datetime
    - last_reply_time: datetime
    """

    def __init__(self, moonlark_main: "MoonlarkMain"):
        self.moonlark_main = moonlark_main

        # 按设计文档的属性
        self.sleep_state: bool = False
        self.sleep_begin_time: Optional[datetime] = None
        self.tiredness: float = 0.0
        self.last_message_time: datetime = datetime.now()
        self.last_reply_time: datetime = datetime.now()

    # ========================================================================
    # 困倦度计算（保持原有算法）
    # ========================================================================

    @staticmethod
    def circadian(hour: float) -> float:
        """生物钟困倦度 B(hour)，0~1"""
        return 0.5 + 0.3 * math.cos(2 * math.pi * (hour - 4) / 24) + 0.1 * math.cos(2 * math.pi * (hour - 14) / 12)

    @staticmethod
    def silence_factor(minutes_since_last_msg: float) -> float:
        """静默因子 S(t)，0~1"""
        return min(1.0, minutes_since_last_msg / 45.0)

    @staticmethod
    def fatigue_factor(consecutive_replies: int) -> float:
        """疲劳因子 F(n)，0~1"""
        return min(1.0, consecutive_replies / 15.0)

    @staticmethod
    def gating(circadian: float) -> float:
        """门控系数 G(B)"""
        return max(0.0, min(1.0, (circadian - 0.4) / 0.4))

    def calculate_sleepiness_index(self) -> float:
        """计算当前困倦度（按设计文档命名）"""
        now = datetime.now()
        hour = now.hour + now.minute / 60.0
        minutes_since_last = (now - self.last_message_time).total_seconds() / 60.0

        b = self.circadian(hour)
        s = self.silence_factor(minutes_since_last)
        f = self.fatigue_factor(self.moonlark_main.consecutive_replies)
        g = self.gating(b)
        epsilon = random.uniform(-0.05, 0.05)

        self.tiredness = max(0.0, min(1.0, 0.50 * b + 0.30 * s + 0.20 * f * g + epsilon))

        logger.debug(
            f"[SleepController] hour={hour:.1f} B={b:.3f} S={s:.3f} "
            f"F={f:.3f} G={g:.3f} ε={epsilon:.3f} → tiredness={self.tiredness:.3f}"
        )
        return self.tiredness

    # ========================================================================
    # 按设计文档的核心方法
    # ========================================================================

    async def request_think(self) -> Optional[dict]:
        """在睡眠状态下由 MoonlarkMain 调用（每 30 分钟）

        输出 {"sleep_decision": "stay_sleep" 或 "wake_up"}
        """
        from nonebot_plugin_openai.utils.chat import fetch_json
        from nonebot_plugin_openai.utils.message import generate_message
        from ...lang import lang

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
                [
                    generate_message(system_prompt, "system"),
                    generate_message(user_prompt, "user"),
                ],
                identify="SleepController - Sleep Think",
                reasoning_effort="low",
            )
            return result
        except Exception as e:
            logger.exception(f"[SleepController] 睡眠决策失败: {e}")
            return None

    async def handle_mention(self, chat_context: list) -> bool:
        """当被提及时调用，输入最近消息上下文

        使用专用 Prompt 判断是否值得醒来。
        返回 True 表示唤醒。
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
                [
                    generate_message(system_prompt, "system"),
                    generate_message(user_prompt, "user"),
                ],
                identify="SleepController - Handle Mention",
                reasoning_effort="low",
            )
            return response.strip().lower() == "wake_up"
        except Exception as e:
            logger.exception(f"[SleepController] mention 判断失败: {e}")
            return False

    def get_sleep_state(self) -> bool:
        """获取睡眠状态"""
        return self.sleep_state

    def handle_message(self) -> None:
        """每次收到消息时调用，更新 last_message_time 并重新计算困倦度"""
        self.last_message_time = datetime.now()
        self.calculate_sleepiness_index()

    def handle_reply(self) -> None:
        """每次发送回复时调用，更新 last_reply_time 并重新计算困倦度"""
        self.last_reply_time = datetime.now()
        self.calculate_sleepiness_index()

    async def handle_tired(self) -> None:
        """困倦度达标时触发

        设置 sleep_state=True，记录 sleep_begin_time，
        通知 MoonlarkMain 切换为睡眠模式（定时器改为 30 分钟）
        """
        self.sleep_state = True
        self.sleep_begin_time = datetime.now()
        self.moonlark_main.state["sleep_mode"] = True
        logger.info("[SleepController] 进入睡眠模式")

    async def process_timer(self) -> None:
        """由 MoonlarkMain 的定时器在清醒时每 10 分钟调用一次

        重新计算困倦度，若超过阈值则调用 handle_tired()
        """
        if self.sleep_state:
            return

        tiredness = self.calculate_sleepiness_index()
        if tiredness >= SLEEP_THRESHOLD:
            logger.info(f"[SleepController] 困倦度 {tiredness:.3f} >= {SLEEP_THRESHOLD}，触发睡眠")
            await self.handle_tired()

    async def wake_up(self) -> None:
        """唤醒：重置睡眠状态"""
        self.sleep_state = False
        self.sleep_begin_time = None
        self.tiredness = 0.0
        self.moonlark_main.state["sleep_mode"] = False
        self.moonlark_main.consecutive_replies = 0
        logger.info("[SleepController] 已唤醒")

    def on_wake_up(self) -> None:
        """兼容旧代码：唤醒回调"""
        self.moonlark_main.consecutive_replies = 0

    # ========================================================================
    # 兼容旧接口
    # ========================================================================

    def check_drowsiness(self, consecutive_replies: int, minutes_since_last_msg: float) -> str:
        """兼容旧代码：检查困倦值"""
        tiredness = self.calculate_sleepiness_index()
        if tiredness >= SLEEP_THRESHOLD:
            return "sleep"
        elif tiredness >= DROWSY_THRESHOLD:
            return "drowsy"
        return "normal"
