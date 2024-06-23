from datetime import datetime
from typing import Optional
from nonebot_plugin_orm import Model
from openai import BaseModel
from sqlalchemy.orm import Mapped, mapped_column

from .config import config


class SessionData(Model):
    session_id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str]
    identifier: Mapped[str]
    activate_code: Mapped[Optional[str]] = mapped_column(nullable=True)
    expiration_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)

class LoginRequest(BaseModel):
    user_id: str
    retention_days: int = config.session_retention_days
