from datetime import date

from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column


class SignData(Model):
    user_id: Mapped[int] = mapped_column(primary_key=True)
    sign_days: Mapped[int] = mapped_column(default=0)
    last_sign: Mapped[date] = mapped_column(default=date(1, 1, 1))
