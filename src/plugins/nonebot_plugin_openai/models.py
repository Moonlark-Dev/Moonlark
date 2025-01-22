from datetime import datetime
from typing import Optional
from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String

from .config import config


class SessionMessage(Model):
    message_id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True)
    session_id: Mapped[int]
    content: Mapped[bytes]
    role: Mapped[str] = mapped_column(String(32))


class GptUser(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    used_token: Mapped[int] = mapped_column(default=0)
