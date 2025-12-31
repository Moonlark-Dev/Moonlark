from datetime import datetime
from typing import Optional

from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import LargeBinary, String, Text, Float, Integer


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


class Sticker(Model):
    """Sticker model for storing saved stickers/memes"""

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    description: Mapped[str] = mapped_column(Text())  # VLM 生成的视觉描述
    raw: Mapped[bytes] = mapped_column(LargeBinary())  # 二进制图片数据
    group_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)  # 来源群聊
    created_time: Mapped[float] = mapped_column(Float())  # 创建时间戳
