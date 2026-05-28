"""睡眠控制器

基于困倦值公式的睡眠管理：
- 困倦度计算（生物钟 + 静默因子 + 疲劳因子 + 门控系数 + 噪声）
- 睡眠状态管理
- @ 唤醒判断
"""

import math
import random
from datetime import datetime
from typing import TYPE_CHECKING

from nonebot import logger

if TYPE_CHECKING:
    from .moonlark_main import MoonlarkMain

DROWSY_THRESHOLD = 0.8
SLEEP_THRESHOLD = 0.95


class SleepController:
    """基于困倦值公式的睡眠控制器

    困倦值 = clamp(0.50 * B + 0.30 * S + 0.20 * F * G + ε, 0, 1)

    B = 生物钟困倦度（余弦组合，模拟夜间高峰 + 午后小困）
    S = 静默因子（距离上一次群内发言的分钟数）
    F = 疲劳因子（连续对话轮数）
    G = 门控系数（疲劳因子只在生物钟困倦度较高时生效）
    ε = 随机噪声 uniform(-0.05, 0.05)
    """

    def __init__(self, moonlark_main: "MoonlarkMain"):
        self.moonlark_main = moonlark_main

    @staticmethod
    def circadian(hour: float) -> float:
        """生物钟困倦度 B(hour)，0~1

        凌晨 4 点最困（~0.9），上午 10 点最清醒（~0.2）
        """
        return 0.5 + 0.3 * math.cos(2 * math.pi * (hour - 4) / 24) + 0.1 * math.cos(2 * math.pi * (hour - 14) / 12)

    @staticmethod
    def silence_factor(minutes_since_last_msg: float) -> float:
        """静默因子 S(t)，0~1

        45 分钟未发言则拉满
        """
        return min(1.0, minutes_since_last_msg / 45.0)

    @staticmethod
    def fatigue_factor(consecutive_replies: int) -> float:
        """疲劳因子 F(n)，0~1

        15 轮后疲劳度达最高
        """
        return min(1.0, consecutive_replies / 15.0)

    @staticmethod
    def gating(circadian: float) -> float:
        """门控系数 G(B)

        B ≤ 0.4 → G = 0（白天完全不生效）
        B ≥ 0.8 → G = 1（深夜完全生效）
        中间线性过渡
        """
        return max(0.0, min(1.0, (circadian - 0.4) / 0.4))

    def calculate_drowsiness(self, consecutive_replies: int, minutes_since_last_msg: float) -> float:
        """计算当前困倦值，0~1"""
        now = datetime.now()
        hour = now.hour + now.minute / 60.0

        b = self.circadian(hour)
        s = self.silence_factor(minutes_since_last_msg)
        f = self.fatigue_factor(consecutive_replies)
        g = self.gating(b)
        epsilon = random.uniform(-0.05, 0.05)

        drowsiness = 0.50 * b + 0.30 * s + 0.20 * f * g + epsilon
        drowsiness = max(0.0, min(1.0, drowsiness))

        logger.debug(
            f"[SleepController] hour={hour:.1f} B={b:.3f} S={s:.3f} "
            f"F={f:.3f} G={g:.3f} ε={epsilon:.3f} → 困倦值={drowsiness:.3f}"
        )
        return drowsiness

    def check_drowsiness(self, consecutive_replies: int, minutes_since_last_msg: float) -> str:
        """检查困倦值并返回行为建议

        Returns:
            "normal" - 正常
            "drowsy" - 触发犯困提示
            "sleep" - 强制触发 sleep 决断
        """
        drowsiness = self.calculate_drowsiness(consecutive_replies, minutes_since_last_msg)

        if drowsiness >= SLEEP_THRESHOLD:
            logger.info(f"[SleepController] 困倦值 {drowsiness:.3f} ≥ {SLEEP_THRESHOLD}，触发睡眠")
            return "sleep"
        elif drowsiness >= DROWSY_THRESHOLD:
            logger.info(f"[SleepController] 困倦值 {drowsiness:.3f} ≥ {DROWSY_THRESHOLD}，触发犯困提示")
            return "drowsy"
        else:
            return "normal"

    def on_wake_up(self) -> None:
        """醒来时重置连续回复计数"""
        self.moonlark_main.consecutive_replies = 0
