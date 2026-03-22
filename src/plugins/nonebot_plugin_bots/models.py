
from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from nonebot_plugin_orm import Model


class UserBotPrivateChatSettings(Model):
    """用户对特定 bot 的私聊设置"""

    __tablename__ = "nonebot_plugin_bots_user_private_chat_settings"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    bot_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    private_chat_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
