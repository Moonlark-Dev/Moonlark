from datetime import datetime
from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column


class QuickMathUser(Model):
    user_id: Mapped[int] = mapped_column(primary_key=True)
    total_point: Mapped[int] = mapped_column(default=0)
    max_point: Mapped[int] = mapped_column(default=0)
    last_use: Mapped[datetime]
