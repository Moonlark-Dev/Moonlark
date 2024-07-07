from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column


class Exchanged(Model):
    user_id: Mapped[int] = mapped_column(primary_key=True)
    pawcoin: Mapped[int] = mapped_column(default=0)
    vimcoin: Mapped[float] = mapped_column(default=0.0)
