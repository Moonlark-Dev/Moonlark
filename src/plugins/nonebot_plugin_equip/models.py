from datetime import datetime

from nonebot_plugin_orm import Model
from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class Equipped(Model):
    """用户装备栏中的一件装备。

    每种装备类型最多只能装备一件；装备数据（如屏障剩余抵挡次数）存放在 data JSON 中。
    """

    __tablename__ = "nonebot_plugin_equip_equipped"

    id_: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    type: Mapped[str] = mapped_column(String(64))
    item_id: Mapped[str] = mapped_column(String(64))
    data: Mapped[str] = mapped_column(Text())
    time: Mapped[datetime] = mapped_column(DateTime)
