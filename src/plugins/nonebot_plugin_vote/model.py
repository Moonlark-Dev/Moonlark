from datetime import datetime

from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column


class Vote(Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    content: Mapped[str]
    sponsor: Mapped[str]
    end_time: Mapped[datetime]
    group: Mapped[str] = mapped_column(nullable=True, default=None)


class Choice(Model):
    _id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id: Mapped[int]
    belong: Mapped[int]
    text: Mapped[str]


class VoteLog(Model):
    _id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    belong: Mapped[int]
    user_id: Mapped[str]
    choice: Mapped[int]
