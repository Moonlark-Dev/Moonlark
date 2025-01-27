from typing import Optional
from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from pydantic import BaseModel

from nonebot_plugin_items.types import DictItemData
from sqlalchemy import String


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
    user_id: Mapped[str] = mapped_column(String(128))
    achievement_namespace: Mapped[str] = mapped_column(String(32))
    achievement_path: Mapped[str] = mapped_column(String(32))
    unlock_progress: Mapped[int]
    unlocked: Mapped[bool]
