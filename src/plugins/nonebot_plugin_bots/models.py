from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from nonebot_plugin_orm import Model


class UserBotPrivateChatSettings(Model):
    """用户对特定 bot 的私聊设置"""

    __tablename__ = "nonebot_plugin_bots_user_private_chat_settings"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    bot_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    private_chat_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class GroupBind(Model):
    """群 QQ 号与群聊 openid 绑定表"""

    __tablename__ = "nonebot_plugin_bots_group_bind"

    # 自增主键
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 群 QQ 号（来自 onebot 11），可为空
    group_qq_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, default=None)
    # 群聊 openid（来自 QQ 官方 bot），可为空
    group_openid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True, default=None)
    # 绑定验证码
    bind_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, default=None)
    # 验证码创建时间
    bind_code_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    # 绑定完成时间
    bound_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    # 记录创建时间
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
