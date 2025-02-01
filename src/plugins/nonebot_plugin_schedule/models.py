from datetime import date
from nonebot_plugin_orm import Model
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import String


class UserSchedule(Model):
    id_: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128))
    task_id: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[date]
    completed_count: Mapped[int] = mapped_column(default=0)
    collected: Mapped[bool] = mapped_column(default=False)
