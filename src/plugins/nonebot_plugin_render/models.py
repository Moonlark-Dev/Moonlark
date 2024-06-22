from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column

class ThemeConfig(Model):
    user_id: Mapped[str] = mapped_column(primary_key=True)
    theme: Mapped[str] = mapped_column(default="default")