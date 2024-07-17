from datetime import datetime
from sqlalchemy import String, Text
from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column


from .config import config


class CaveData(Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    author: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text())
    time: Mapped[datetime]
    public: Mapped[bool] = mapped_column(default=not config.cave_need_review)


class ImageData(Model):
    id: Mapped[float] = mapped_column(primary_key=True)
    data: Mapped[bytes]
    name: Mapped[str] = mapped_column(String(128), default="image.png")
    belong: Mapped[int]


class GroupData(Model):
    group_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_use: Mapped[datetime] = mapped_column(default=datetime.fromtimestamp(0))
    cool_down_time: Mapped[float] = mapped_column(default=60)


class UserCoolDownData(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_use: Mapped[datetime] = mapped_column(default=datetime.fromtimestamp(0))
