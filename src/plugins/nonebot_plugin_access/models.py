from nonebot_plugin_orm import Model
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class SubjectData(Model):
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(256))
    name: Mapped[str] = mapped_column(String(128))
    available: Mapped[bool]
