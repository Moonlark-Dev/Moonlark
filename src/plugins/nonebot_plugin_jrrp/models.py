"""用户每日人品值 ORM 模型."""

from datetime import date

from nonebot_plugin_orm import Model
from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class LuckTrend(Model):  # pylint: disable=too-few-public-methods
    """用户每日人品值记录，用于走势图."""

    __tablename__ = "nonebot_plugin_jrrp_lucktrend"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    record_date: Mapped[date] = mapped_column(Date, primary_key=True)
    luck_value: Mapped[int] = mapped_column(Integer)
    reroll_count: Mapped[int] = mapped_column(Integer, default=0)
