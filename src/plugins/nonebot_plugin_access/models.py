from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column


class SubjectData(Model):
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject: Mapped[str]
    name: Mapped[str]
    available: Mapped[bool]
