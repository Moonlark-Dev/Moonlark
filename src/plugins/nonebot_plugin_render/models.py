from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String


class ThemeConfig(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    theme: Mapped[str] = mapped_column(String(128), default="default")
