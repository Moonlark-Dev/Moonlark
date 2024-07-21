from nonebot_plugin_orm import Model
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import String


class User(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_name: Mapped[str] = mapped_column(String(256))
