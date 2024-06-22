from typing import Optional, TypedDict

from .models import AchievementData


class AchievementUnlockData(TypedDict):
    progress: int
    unlocked: bool

class UserAchievementData(TypedDict):
    user_id: str
    achievement: AchievementData
    name: str
    description: Optional[str]
    unlock: AchievementUnlockData