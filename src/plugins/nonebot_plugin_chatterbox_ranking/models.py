from nonebot_plugin_orm import Model
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import String
from pydantic import BaseModel


class GroupChatterbox(Model):
    id_: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128))
    group_id: Mapped[str] = mapped_column(String(128))
    message_count: Mapped[int]


class GroupChatterboxWithNickname(BaseModel):
    nickname: str
    message_count: int
