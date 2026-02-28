from datetime import datetime
from nonebot_plugin_orm import Model
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column


class LastSeenRecord(Model):
    """用户最后上线时间记录模型
    
    使用复合主键 (user_id, session_id)：
    - session_id = "global": 全局最后上线时间
    - session_id = get_group_id(): 特定会话的最后上线时间
    """

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = {"extend_existing": True}
