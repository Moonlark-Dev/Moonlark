from datetime import datetime
from typing import Optional

from nonebot_plugin_orm import Model
from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class BuffAttachment(Model):
    """用户身上的一次 buff 附着。

    同一用户 + 同一 buff 只保留一行：不支持叠加的 buff 重新附着时刷新，
    支持叠加的 buff 重新附着时增加层数（不超过定义中的 max_layers）。

    - `expires_at` 为时间维度：到期后 buff 消失，`None` 表示不按时间消失；
    - `remaining_count` 为次数维度：触发 `remaining_count` 次后消失，
      `None` 表示不按次数消失；
    - 两个维度可以同时存在，任意一个耗尽即整个 buff 消失。
    """

    __tablename__ = "nonebot_plugin_buff_attachment"
    __table_args__ = (UniqueConstraint("user_id", "buff_id", name="uq_nonebot_plugin_buff_attachment_user_buff"),)

    id_: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    buff_id: Mapped[str] = mapped_column(String(128), index=True)
    # 当前层数，至少为 1
    layers: Mapped[int] = mapped_column(Integer, default=1)
    # 时间维度：到期时间
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    # 次数维度：剩余可触发次数
    remaining_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
