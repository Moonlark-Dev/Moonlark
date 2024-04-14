from sqlalchemy.orm import Mapped, mapped_column
from nonebot_plugin_orm import Model
from datetime import datetime
from .config import config

class RemovedCave(Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    expiration_time: Mapped[datetime]
    superuser: Mapped[bool]  = mapped_column(default=False)

