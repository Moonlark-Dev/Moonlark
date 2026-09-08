from datetime import datetime

from nonebot_plugin_orm import Model
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


class AttackRecord(Model):
    __tablename__ = "nonebot_plugin_eggstrike_attackrecord"

    id_: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    target_id: Mapped[str] = mapped_column(String(128), index=True)
    count: Mapped[int] = mapped_column(default=1)
    egg_id: Mapped[str] = mapped_column(String(128))
    time: Mapped[datetime] = mapped_column(DateTime, index=True)


class EggSelection(Model):
    """用户当前选择的默认鸡蛋种类"""

    __tablename__ = "nonebot_plugin_eggstrike_eggselection"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    egg_id: Mapped[str] = mapped_column(String(128))
