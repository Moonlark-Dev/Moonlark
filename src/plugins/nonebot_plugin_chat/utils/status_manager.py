from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class MoodEnum(str, Enum):
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    TRUST = "trust"
    ANTICIPATION = "anticipation"
    CALM = "calm"
    BORED = "bored"
    CONFUSED = "confused"
    TIRED = "tired"
    SHY = "shy"


class StatusManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StatusManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._mood: MoodEnum = MoodEnum.CALM
        self._mood_reason: Optional[str] = None
        self._last_mood_update: datetime = datetime.now()
        self._activity: str = "daze"
        self._activity_time: datetime = datetime.now()
        self._activity_expire: datetime = datetime.now() + timedelta(minutes=10)
        self._initialized = True

    def set_mood(self, mood: MoodEnum, reason: Optional[str] = None) -> tuple[bool, str]:
        """
        设置心情
        :param mood: 心情枚举
        :param reason: 心情原因
        :return: (是否成功, 提示信息)
        """
        now = datetime.now()
        # 冷却时间检查 (5分钟)
        if now - self._last_mood_update < timedelta(minutes=5) and self._mood != MoodEnum.CALM:
            return False, "status.mood_cooldown"

        self._mood = mood
        self._mood_reason = reason
        self._last_mood_update = now
        return True, "status.mood_set"

    def set_activity(self, activity: str, duration: int = 10) -> None:
        """
        设置正在做的事
        :param activity: 正在做的事
        :param duration: 持续时间（分钟）
        """
        self._activity = activity
        self._activity_time = datetime.now()
        self._activity_expire = datetime.now() + timedelta(minutes=duration)

    def get_status(self) -> tuple[MoodEnum, Optional[str], str, int]:
        """
        获取状态信息
        :return: (心情, 心情原因, 活动, 剩余时间)
        """
        now = datetime.now()
        
        # 计算活动剩余时间
        if now > self._activity_expire:
            activity = "daze"
            remain_minutes = 0
        else:
            activity = self._activity
            remain_minutes = int((self._activity_expire - now).total_seconds() / 60)
            
        return self._mood, self._mood_reason, activity, remain_minutes

def get_status_manager() -> StatusManager:
    return StatusManager()
