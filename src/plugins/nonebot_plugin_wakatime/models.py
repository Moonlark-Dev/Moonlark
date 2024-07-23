from typing import Literal
from nonebot_plugin_orm import Model
from pydantic import BaseModel
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import String, Double


class User(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    access_token: Mapped[str] = mapped_column(String(256))
    expired_at: Mapped[float] = mapped_column(Double())


class StatsProject(BaseModel):
    name: str
    text: str


class StatsData(BaseModel):
    start: str
    end: str
    human_readable_total: str
    status: Literal["ok"]
    human_readable_total_including_other_language: str
    total_seconds: float
    username: str
    projects: list[StatsProject]


class StatsResponse(BaseModel):
    data: StatsData


class TokenResponse(BaseModel):
    access_token: str
    expires_in: int
