from datetime import datetime
from typing import Optional
from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column

from .config import config


class User(Model):
    user_id: Mapped[int] = mapped_column(primary_key=True)
    tokens: Mapped[int] = mapped_column(default=config.openai_free_token)
    free_count: Mapped[int] = mapped_column(default=0)
    plus: Mapped[Optional[datetime]] = mapped_column(nullable=True, default=None)
