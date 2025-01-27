from datetime import datetime
from typing import Literal, Optional
from nonebot_plugin_orm import Model
from pydantic import BaseModel
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import String, Text

from nonebot_plugin_items.types import DictItemData


class EmailData(Model):
    __table_args__ = {"extend_existing": True}
    email_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    author: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, default=None)
    content: Mapped[str] = mapped_column(Text())
    subject: Mapped[str] = mapped_column(String(256))
    time: Mapped[datetime]


class EmailItem(Model):
    __table_args__ = {"extend_existing": True}
    id_: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    belong: Mapped[int]
    item_id: Mapped[str] = mapped_column(String(64))
    count: Mapped[int]
    data: Mapped[str] = mapped_column(Text())


class EmailUser(Model):
    __table_args__ = {"extend_existing": True}
    id_: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    is_claimed: Mapped[bool] = mapped_column(default=False)
    is_read: Mapped[bool] = mapped_column(default=False)
    user_id: Mapped[str] = mapped_column(String(128))
    email_id: Mapped[int]


class EmailDataArgs(BaseModel):
    subject: str
    content: str
    receivers: list[str] | Literal["*"]
    sender: Optional[str] = None
    items: list[DictItemData] = []


class EmailEditArgs(BaseModel):
    subject: Optional[str] = None
    content: Optional[str] = None
