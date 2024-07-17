from datetime import datetime
from typing import Optional
from nonebot_plugin_orm import Model
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class UserData(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(256))
    register_time: Mapped[Optional[datetime]] = mapped_column(nullable=True, default=None)
    ship_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, default=None)
    gender: Mapped[Optional[bool]] = mapped_column(nullable=True, default=None)
    experience: Mapped[int] = mapped_column(default=0)
    vimcoin: Mapped[float] = mapped_column(default=0.0)
    health: Mapped[float] = mapped_column(default=100.0)
    favorability: Mapped[float] = mapped_column(default=0.0)
