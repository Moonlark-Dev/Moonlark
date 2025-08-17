from datetime import datetime
from nonebot_plugin_orm import Model
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import String, Text


class GroupMessage(Model):
    id_: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message: Mapped[str] = mapped_column(Text())
    sender_nickname: Mapped[str] = mapped_column(String(128))
    group_id: Mapped[str] = mapped_column(String(128))
    timestamp: Mapped[datetime] = mapped_column(default_factory=datetime.now)
