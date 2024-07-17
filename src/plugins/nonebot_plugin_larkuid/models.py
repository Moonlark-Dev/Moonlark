from datetime import datetime
from typing import Optional
from nonebot_plugin_orm import Model
from openai import BaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, String

from .config import config


class SessionData(Model):
    session_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128))
    identifier: Mapped[str] = mapped_column(String(256))
    activate_code: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    expiration_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)


class LoginRequest(BaseModel):
    user_id: str
    retention_days: int = config.session_retention_days
