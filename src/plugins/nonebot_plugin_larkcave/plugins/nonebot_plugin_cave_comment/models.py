from sqlalchemy.orm import Mapped, mapped_column
from nonebot_plugin_orm import Model
from datetime import datetime
from sqlalchemy import String, Text


class CommentData(Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    author: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text)
    time: Mapped[datetime]
    belong: Mapped[int]
