from typing import Literal

from nonebot_plugin_orm import Model
from pydantic import BaseModel
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import String


class User(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_name: Mapped[str] = mapped_column(String(256))


class DurationsProject(BaseModel):
    name: str
    text: str


class DurationsData(BaseModel):
    start: str
    end: str
    human_readable_total: str
    status: Literal["ok"]
    human_readable_total_including_other_language: str
    total_seconds: float
    username: str
    projects: list[DurationsProject]


class DurationsResponse(BaseModel):
    data: DurationsData
