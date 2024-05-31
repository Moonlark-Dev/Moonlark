from datetime import datetime
from typing import Optional

from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column


class SessionData(Model):
    session_id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str]
    user_agent: Mapped[str]
    activate_code: Mapped[Optional[str]] = mapped_column(nullable=True)
    expiration_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)
