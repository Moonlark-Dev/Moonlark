from datetime import date

from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String


class SignData(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sign_days: Mapped[int] = mapped_column(default=0)
    last_sign: Mapped[date] = mapped_column(default=date(1, 1, 1))
    # 自动签到：是否开启
    auto_enabled: Mapped[bool] = mapped_column(default=False)
    # 自动签到：允许使用的自动签到券个数（<= 0 为不限制）
    auto_limit: Mapped[int] = mapped_column(default=0)
    # 自动签到：自上次重置后已使用的自动签到券数量
    auto_used: Mapped[int] = mapped_column(default=0)
    # 自动签到：累计自动签到次数
    auto_count: Mapped[int] = mapped_column(default=0)
