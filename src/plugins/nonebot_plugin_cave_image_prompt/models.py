from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from nonebot_plugin_orm import Model


class CaveImagePromptConfig(Model):
    """记录用户私聊单图投稿询问功能的开关状态，默认关闭"""

    __tablename__ = "nonebot_plugin_cave_image_prompt_config"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=False)
