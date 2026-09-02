from datetime import datetime, timezone
from typing import Optional

from pydantic import Field
from nonebot_plugin_orm import Model
from openai import BaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, LargeBinary, String

from .config import config


def _utcnow() -> datetime:
    """UTC naive 时间基准（与 SessionData 的时间口径一致）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


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


class PasskeyCredential(Model):
    """用户注册的 Passkey（WebAuthn）公钥凭据。"""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    credential_id: Mapped[bytes] = mapped_column(LargeBinary(length=768), unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    device_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)


class PasskeyChallenge(Model):
    """一次 WebAuthn 仪式使用的挑战（一次性、有过期时间）。"""

    challenge: Mapped[str] = mapped_column(String(64), primary_key=True)  # 32 字节随机数的 hex
    purpose: Mapped[str] = mapped_column(String(16))  # register / login
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # 注册时为该用户，登录时可空
    origin: Mapped[str] = mapped_column(String(256))  # 期望的 WebAuthn origin
    rp_id: Mapped[str] = mapped_column(String(256))  # 期望的 Relying Party ID
    expires_at: Mapped[datetime] = mapped_column()


class LoginRequest(BaseModel):
    user_id: str
    retention_days: int = Field(default=config.session_retention_days, ge=1, le=config.session_max_lifetime_days)
