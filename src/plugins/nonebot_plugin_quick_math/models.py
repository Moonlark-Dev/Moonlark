from datetime import datetime
from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String


class QuickMathUser(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    experience: Mapped[int] = mapped_column(default=0)
    max_point: Mapped[int] = mapped_column(default=0)
    last_use: Mapped[datetime]
    exchanged: Mapped[int] = mapped_column(defalut=0)
