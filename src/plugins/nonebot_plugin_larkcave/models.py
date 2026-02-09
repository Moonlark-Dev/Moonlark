from datetime import datetime
from sqlalchemy import String, Text, Double, LargeBinary
from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from pydantic import BaseModel

from .config import config

from sqlalchemy.dialects.mysql import LONGBLOB
CompatibleBlob = LargeBinary().with_variant(LONGBLOB(), "mysql")

class CaveData(Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    author: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text())
    time: Mapped[datetime]
    public: Mapped[bool] = mapped_column(default=not config.cave_need_review)


class ImageData(Model):
    id: Mapped[float] = mapped_column(Double(), primary_key=True)
    name: Mapped[str] = mapped_column(Text())
    belong: Mapped[int]
    p_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    image_data: Mapped[bytes] = mapped_column(CompatibleBlob, nullable=True)


class CaveImage(BaseModel):
    id_: float
    data: bytes
    name: str


class UserCoolDownData(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_use: Mapped[datetime] = mapped_column(default=datetime.fromtimestamp(0))


class RemovedCave(Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    expiration_time: Mapped[datetime]
    superuser: Mapped[bool] = mapped_column(default=False)


class CommentData(Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    author: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text)
    time: Mapped[datetime]
    belong: Mapped[int]
