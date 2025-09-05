from datetime import datetime
from typing import Optional
from nonebot_plugin_orm import Model
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class UserData(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(256))
    register_time: Mapped[datetime]
    experience: Mapped[int] = mapped_column(default=0)
    vimcoin: Mapped[float] = mapped_column(default=0.0)
    health: Mapped[float] = mapped_column(default=100.0)
    favorability: Mapped[float] = mapped_column(default=0.0)
    config: Mapped[bytes] = mapped_column(default=b"e30=")


class GuestUser(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(256))

