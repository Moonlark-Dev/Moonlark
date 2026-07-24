from datetime import date

from nonebot_plugin_orm import Model
from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class LuckTrend(Model):
    """记录用户每日人品值，用于走势图"""

    __tablename__ = "nonebot_plugin_jrrp_lucktrend"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    record_date: Mapped[date] = mapped_column(Date, primary_key=True)
    luck_value: Mapped[int] = mapped_column(Integer)
    reroll_count: Mapped[int] = mapped_column(Integer, default=0)
