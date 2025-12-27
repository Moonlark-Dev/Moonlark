from datetime import datetime
from typing import Optional

from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import BigInteger, String, Text, Float, Integer


class SessionMessage(Model):
    id_: Mapped[int] = mapped_column(autoincrement=True, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text())
    role: Mapped[str] = mapped_column(String(16))


class ChatUser(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    latest_chat: Mapped[datetime]


class ChatGroup(Model):
    group_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    blocked_user: Mapped[str] = mapped_column(Text(), default="[]")
    enabled: Mapped[bool]


class Note(Model):
    """Note model for storing user-generated notes with optional expiration and keywords"""

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    context_id: Mapped[str] = mapped_column(String(128), index=True)  # user_id for private, group_id for groups
    content: Mapped[str] = mapped_column(Text())
    keywords: Mapped[str] = mapped_column(String(length=256), default="")
    created_time: Mapped[float] = mapped_column(Float())
    expire_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)  # Optional expiration time
