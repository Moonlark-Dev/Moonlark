from datetime import datetime
from typing import Optional
from nonebot_plugin_orm import Model
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import String, DateTime, Index


class OnlineTimeRecord(Model):
    """用户在线时间记录模型"""

    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime, index=True)

    # 创建索引以提高查询性能
    __table_args__ = (
        Index("idx_user_id", "user_id"),
        Index("idx_start_time", "start_time"),
        Index("idx_end_time", "end_time"),
        {"extend_existing": True},
    )
