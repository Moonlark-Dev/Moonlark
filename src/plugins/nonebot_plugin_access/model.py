from sqlalchemy.orm import Mapped, mapped_column
from nonebot_plugin_orm import Model


class SubjectData(Model):
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject: Mapped[str]
    name: Mapped[str]
    available: Mapped[bool]
