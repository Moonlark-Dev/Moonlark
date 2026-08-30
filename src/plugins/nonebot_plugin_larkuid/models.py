from datetime import datetime
from typing import Optional

from pydantic import Field
from nonebot_plugin_orm import Model
from openai import BaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String

from .config import config


class SessionData(Model):
    session_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128))
    identifier: Mapped[str] = mapped_column(String(256))
    activate_code: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    expiration_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    # 会话元数据：created_at 是绝对寿命上限的锚点，last_active_at / device 用于设备管理展示。
    # 均可空以兼容存量数据；存量行缺少锚点时不套用绝对上限，行为与旧版一致。
    created_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_active_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    device: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)


class LoginRequest(BaseModel):
    user_id: str
    retention_days: int = Field(default=config.session_retention_days, ge=1, le=config.session_max_lifetime_days)
