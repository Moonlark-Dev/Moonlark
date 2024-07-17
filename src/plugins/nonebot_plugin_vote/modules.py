from datetime import datetime

from nonebot_plugin_orm import Model
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column


class Vote(Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text())
    content: Mapped[str] = mapped_column(Text())
    sponsor: Mapped[str] = mapped_column(String(128))
    end_time: Mapped[datetime]
    group: Mapped[str] = mapped_column(String(128), nullable=True, default=None)


class Choice(Model):
    _id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id: Mapped[int]
    belong: Mapped[int]
    text: Mapped[str] = mapped_column(Text())


class VoteLog(Model):
    _id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    belong: Mapped[int]
    user_id: Mapped[str] = mapped_column(String(128))
    choice: Mapped[int]
