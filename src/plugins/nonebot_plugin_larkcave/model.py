from sqlalchemy.orm import Mapped, mapped_column
from nonebot_plugin_orm import Model
from datetime import datetime
from .config import config

class CaveData(Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    author: Mapped[str]
    content: Mapped[str]
    time: Mapped[datetime]
    public: Mapped[bool] = mapped_column(default=not config.cave_need_review)


class ImageData(Model):
    id: Mapped[float] = mapped_column(primary_key=True)
    data: Mapped[bytes]
    name: Mapped[str] = mapped_column(default="image.png")
    belong: Mapped[int]

