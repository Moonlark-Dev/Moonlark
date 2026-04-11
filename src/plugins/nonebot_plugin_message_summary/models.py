from datetime import datetime, date
from nonebot_plugin_orm import Model
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import String, Text, Integer
from typing import TypedDict


class GroupMessage(Model):
    id_: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message: Mapped[str] = mapped_column(Text())
    sender_nickname: Mapped[str] = mapped_column(String(128))
    user_id: Mapped[str] = mapped_column(String(128))
    group_id: Mapped[str] = mapped_column(String(128))
    timestamp: Mapped[datetime] = mapped_column(default=datetime.now)


class MVPRecord(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    group_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    mvp_count: Mapped[int] = mapped_column(Integer(), default=0)


class CatGirlScore(TypedDict):
    rank: int
    username: str
    score: int


class DebateParty(TypedDict):
    name: str
    standpoint: str
    arguments: list[str]
    implicit: str
    fallacies: str


class DebateAnalysisResult(TypedDict):
    conclusion: str


class DebateAnalysis(TypedDict):
    topic: str
    conflict_type: str
    parties: list[DebateParty]
    analysis: DebateAnalysisResult
