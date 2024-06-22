from typing import Optional
from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from pydantic import BaseModel

from ..nonebot_plugin_item.types import DictItemData


class AchievementLangConfig(BaseModel):
    plugin: str
    key: str


class AchievementData(BaseModel):
    key: Optional[str] = None
    required_unlock_count: int
    awards: list[DictItemData]
    description: bool = False


class AchievementList(BaseModel):
    lang: AchievementLangConfig
    achievements: dict[str, AchievementData]


class User(Model):
    _id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str]
    achievement_namespace: Mapped[str]
    achievement_path: Mapped[str]
    unlock_progress: Mapped[int]
    unlocked: Mapped[bool]
