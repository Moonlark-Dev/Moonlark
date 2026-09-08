from datetime import datetime
from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String


class QuickMathUser(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    experience: Mapped[int] = mapped_column(default=0)
    max_point: Mapped[int] = mapped_column(default=0)
    last_use: Mapped[datetime]
    exchanged: Mapped[int] = mapped_column(default=0)


class QuickMathWeek(Model):
    """按 ISO 周累计的 Quick Math 积分，用于主界面的周积分排行榜。"""

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    week: Mapped[str] = mapped_column(String(16), primary_key=True, index=True)
    points: Mapped[int] = mapped_column(default=0)
