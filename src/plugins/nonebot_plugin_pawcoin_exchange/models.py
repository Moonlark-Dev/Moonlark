from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String


class Exchanged(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    pawcoin: Mapped[int] = mapped_column(default=0)
    vimcoin: Mapped[float] = mapped_column(default=0.0)
