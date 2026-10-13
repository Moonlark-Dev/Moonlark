from datetime import datetime
from typing import Optional
from nonebot_plugin_orm import Model
from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class UserData(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(256))
    register_time: Mapped[datetime]
    experience: Mapped[int] = mapped_column(default=0)
    # 显式指定 Float()：SQLAlchemy 2.1 起 Mapped[float] 的默认映射由 Float 变为 Double，
    # 不写显式类型会让 nb orm check 把现有 FLOAT 列判成待迁移（详见迁移文件中的 sa.Float()）
    vimcoin: Mapped[float] = mapped_column(Float(), default=0.0)
    health: Mapped[float] = mapped_column(Float(), default=100.0)
    downed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    death_count: Mapped[int] = mapped_column(default=0)
    favorability: Mapped[float] = mapped_column(Float(), default=0.0)
    config: Mapped[str] = mapped_column(Text(), default="{}")


class GuestUser(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(256))
