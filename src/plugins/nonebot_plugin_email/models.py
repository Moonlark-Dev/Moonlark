from datetime import datetime
from typing import Optional
from nonebot_plugin_orm import Model
from sqlalchemy.orm import mapped_column, Mapped


class Email(Model):
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    author: Mapped[Optional[str]] = mapped_column(nullable=True, default=None)
    content: Mapped[str]
    subject: Mapped[str]
    time: Mapped[datetime]


class EmailItem(Model):
    id_: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    belong: Mapped[int]
    item_id: Mapped[str]
    count: Mapped[int]
    data: Mapped[str]


class EmailUser(Model):
    id_: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    is_claimed: Mapped[bool] = mapped_column(default=False)
    is_read: Mapped[bool] = mapped_column(default=False)
    user_id: Mapped[str]
    email_id: Mapped[int]
