from sqlalchemy.orm import Mapped, mapped_column
from nonebot_plugin_orm import Model
from datetime import datetime


class CommentData(Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    author: Mapped[str]
    content: Mapped[str]
    time: Mapped[datetime]
    belong: Mapped[int]
