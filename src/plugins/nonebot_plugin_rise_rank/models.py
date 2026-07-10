from datetime import date, datetime

from nonebot_plugin_orm import Model
from sqlalchemy import Boolean, Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


class RiseData(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    record_date: Mapped[date] = mapped_column(Date, primary_key=True)
    wake_time: Mapped[datetime] = mapped_column(DateTime)
    valid: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = {"extend_existing": True}
