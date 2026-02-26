from datetime import datetime, timedelta
from typing import Optional

from nonebot_plugin_chat.types import MoodEnum


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
        self.mood_retention_rate: float = 1.0
        self._initialized = True

    def get_mood_retention(self) -> float:
        return 4 ** -(self.mood_retention_rate * (datetime.now() - self._last_mood_update).total_seconds() / 60)

    def set_mood(self, mood: MoodEnum, reason: Optional[str] = None) -> tuple[bool, str]:
        """
        设置心情
        :param mood: 心情枚举
        :param reason: 心情原因
        :return: (是否成功, 提示信息)
        """
        dt = datetime.now()
        mood_retention = self.get_mood_retention()
        if mood_retention >= 0.3:
            self._last_mood_update -= timedelta(seconds=10)
            return False, "status.mood_set"
        elif mood_retention >= 0.1:
            self.mood_retention_rate = 2
        else:
            self.mood_retention_rate = 1
        self._mood = mood
        self._mood_reason = reason
        self._last_mood_update = dt
        return True, "status.mood_set"

    def get_status(self) -> tuple[MoodEnum, Optional[str]]:
        """
        获取状态信息
        :return: (心情, 心情原因)
        """
        return self._mood, self._mood_reason


def get_status_manager() -> StatusManager:
    return StatusManager()
