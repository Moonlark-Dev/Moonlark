from datetime import datetime

from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text



class SessionMessage(Model):
    id_: Mapped[int] = mapped_column(autoincrement=True, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text())
    role: Mapped[str] = mapped_column(String(16))


class ChatUser(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    memory: Mapped[str] = mapped_column(Text(), default="None")
    latest_chat: Mapped[datetime]


