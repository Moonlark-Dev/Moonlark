from datetime import datetime

from nonebot_plugin_orm import Model
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


class CraftingMachine(Model):
    """用户的合成机：等级决定可以同时进行的合成数量"""

    __tablename__ = "nonebot_plugin_craft_machine"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    level: Mapped[int] = mapped_column(default=1)


class CraftingJob(Model):
    """合成机中正在进行的合成任务"""

    __tablename__ = "nonebot_plugin_craft_job"

    id_: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    recipe_id: Mapped[str] = mapped_column(String(64))
    time: Mapped[datetime] = mapped_column(DateTime)
    finish_time: Mapped[datetime] = mapped_column(DateTime, index=True)
