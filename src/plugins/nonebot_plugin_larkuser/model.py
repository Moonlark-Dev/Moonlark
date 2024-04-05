from sqlalchemy.orm import Mapped, mapped_column
from nonebot_plugin_orm import Model
from datetime import datetime

class UserData(Model):
    user_id: Mapped[str] = mapped_column(primary_key=True)
    nickname: Mapped[str]
    activation_time: Mapped[datetime]
    avatar: Mapped[bytes] = mapped_column(nullable=True, default=None)
    experience: Mapped[int] = mapped_column(default=0)
    vimcoin: Mapped[float] = mapped_column(default=0.0)
    health: Mapped[float] = mapped_column(default=100.0)
    favorability: Mapped[float] = mapped_column(default=0.0)

