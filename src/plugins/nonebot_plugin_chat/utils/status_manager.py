from datetime import datetime, timedelta
import math
from typing import Optional, TypedDict

from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_chat.enums import MoodEnum


class EmotionData(TypedDict):
    name: str
    included_labels: list[str]
    # PAD 中心
    center: tuple[float, float, float]
    mood_enum: MoodEnum


EMOTION_LIST = [
    EmotionData(
        name="joy",
        included_labels=["joy", "anticipation"],
        center=(0.7, 0.5, 0.4),
        mood_enum=MoodEnum.JOY,
    ),
    EmotionData(
        name="sadness",
        included_labels=["sadness", "tired"],
        center=(-0.5, -0.4, -0.3),
        mood_enum=MoodEnum.SADNESS,
    ),
    EmotionData(
        name="anger",
        included_labels=["anger", "disgust"],
        center=(-0.6, 0.6, 0.3),
        mood_enum=MoodEnum.ANGER,
    ),
    EmotionData(
        name="fear",
        included_labels=["fear", "shy"],
        center=(-0.4, 0.4, -0.6),
        mood_enum=MoodEnum.FEAR,
    ),
    EmotionData(
        name="surprise",
        included_labels=["surprise"],
        center=(0.4, 0.8, 0.0),
        mood_enum=MoodEnum.SURPRISE,
    ),
    EmotionData(
        name="calm",
        included_labels=["calm", "trust"],
        center=(0.3, -0.3, 0.2),
        mood_enum=MoodEnum.CALM,
    ),
    EmotionData(
        name="bored",
        included_labels=["bored"],
        center=(-0.2, -0.5, -0.2),
        mood_enum=MoodEnum.BORED,
    ),
    EmotionData(
        name="confused",
        included_labels=["confused"],
        center=(-0.3, 0.1, -0.4),
        mood_enum=MoodEnum.CONFUSED,
    ),
]

MOOD_DELTA_PAD: dict[str, tuple[float, float, float]] = {
    "joy": (0.4, 0.3, 0.2),
    "sadness": (-0.4, -0.2, -0.3),
    "anger": (-0.3, 0.4, 0.3),
    "fear": (-0.3, 0.4, -0.4),
    "surprise": (0.2, 0.5, 0.0),
    "disgust": (-0.4, 0.2, 0.1),
    "trust": (0.3, -0.1, 0.2),
    "anticipation": (0.2, 0.3, 0.1),
    "calm": (0.2, -0.4, 0.1),
    "bored": (-0.2, -0.4, -0.2),
    "confused": (-0.1, 0.2, -0.3),
    "tired": (-0.1, -0.5, -0.2),
    "shy": (-0.1, 0.1, -0.4),
}


class StatusManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StatusManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    async def process_timer(self) -> None:
        factor = math.exp(- 15 * math.log(2) / 10 * 60)
        self.pad_pos = (
            self.pad_pos[0] * factor,
            self.pad_pos[1] * factor,
            self.pad_pos[2] * factor,
        )

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.pad_pos = (0.0, 0.0, 0.0)
        self._mood_reason: Optional[str] = None
        scheduler.scheduled_job("interval", seconds=15, id="status_manager_process_timer")(self.process_timer)

    def get_mood_retention(self) -> float:
        mood_type = self.get_mood_type()
        mood_data = [e for e in EMOTION_LIST if e["mood_enum"] == mood_type][0]
        return max(
            0,
            1
            - math.sqrt(
                (mood_data["center"][0] - self.pad_pos[0]) ** 2
                + (mood_data["center"][1] - self.pad_pos[1]) ** 2
                + (mood_data["center"][2] - self.pad_pos[2]) ** 2
            )
            / 1.5,
        )

    def set_mood(self, mood: MoodEnum, reason: Optional[str] = None, intensity: float = 0.5) -> None:
        mood_id = mood.value
        mood_pad = MOOD_DELTA_PAD[mood_id]
        self.pad_pos = (
            max(min(self.pad_pos[0] + mood_pad[0] * intensity, -1), 1),
            max(min(self.pad_pos[1] + mood_pad[1] * intensity, -1), 1),
            max(min(self.pad_pos[2] + mood_pad[2] * intensity, -1), 1),
        )
        self._mood_reason = reason

    def get_status(self) -> tuple[MoodEnum, Optional[str]]:
        return self.get_mood_type(), self._mood_reason

    def get_mood_type(self) -> MoodEnum:
        return sorted(
            EMOTION_LIST,
            key=lambda x: math.sqrt(
                (x["center"][0] - self.pad_pos[0]) ** 2
                + (x["center"][1] - self.pad_pos[1]) ** 2
                + (x["center"][2] - self.pad_pos[2]) ** 2
            ),
        )[0]["mood_enum"]


def get_status_manager() -> StatusManager:
    return StatusManager()
