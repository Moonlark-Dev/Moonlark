from datetime import datetime

from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, Float, Integer


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


class MemoryNode(Model):
    """Memory graph node representing a concept with associated memories"""

    concept: Mapped[str] = mapped_column(String(256), primary_key=True)
    context_id: Mapped[str] = mapped_column(String(128), primary_key=True)  # user_id for private, group_id for groups
    memory_items: Mapped[str] = mapped_column(Text(), default="")
    weight: Mapped[float] = mapped_column(Float(), default=1.0)
    created_time: Mapped[float] = mapped_column(Float())
    last_modified: Mapped[float] = mapped_column(Float())
    hash_value: Mapped[int] = mapped_column(Integer(), default=0)


class MemoryEdge(Model):
    """Memory graph edge representing relationships between concepts"""

    source: Mapped[str] = mapped_column(String(256), primary_key=True)
    target: Mapped[str] = mapped_column(String(256), primary_key=True)
    context_id: Mapped[str] = mapped_column(String(128), primary_key=True)  # user_id for private, group_id for groups
    strength: Mapped[int] = mapped_column(Integer(), default=1)
    created_time: Mapped[float] = mapped_column(Float())
    last_modified: Mapped[float] = mapped_column(Float())
    hash_value: Mapped[int] = mapped_column(Integer(), default=0)
