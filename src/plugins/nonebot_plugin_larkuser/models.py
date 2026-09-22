from datetime import datetime
from typing import Optional
from nonebot_plugin_orm import Model
from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class UserData(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(256))
    register_time: Mapped[datetime]
    experience: Mapped[int] = mapped_column(default=0)
    vimcoin: Mapped[float] = mapped_column(default=0.0)
    health: Mapped[float] = mapped_column(default=100.0)
    downed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    death_count: Mapped[int] = mapped_column(default=0)
    favorability: Mapped[float] = mapped_column(default=0.0)
    config: Mapped[str] = mapped_column(Text(), default="{}")


class GuestUser(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(256))


class QQGroupInfo(Model):
    """QQ 官方 Bot 群聊缓存（群基本信息 + 群成员同步状态）

    ``group_openid`` 由 QQ 开放平台按应用分配，同一个群在不同 Bot（不同 AppID）
    下会有不同的 openid，因此这里把发现该群的 Bot 一并记录下来。
    """

    __tablename__ = "nonebot_plugin_larkuser_qq_group_info"

    group_openid: Mapped[str] = mapped_column(String(128), primary_key=True)
    bot_id: Mapped[str] = mapped_column(String(64), default="")
    group_name: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(String(512), default="")
    member_count: Mapped[int] = mapped_column(Integer(), default=0)
    # 最后一次群信息刷新时间（无论成功与否，用于控制接口调用频率）
    info_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    # 最后一次群成员列表同步时间（无论成功与否，用于控制接口调用频率）
    members_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    # 最近一次同步失败的原因，空串表示最近一次同步成功
    last_error: Mapped[str] = mapped_column(String(512), default="")


class QQGroupMember(Model):
    """QQ 官方 Bot 群成员缓存（来自 /v2/groups/{group_openid}/members）"""

    __tablename__ = "nonebot_plugin_larkuser_qq_group_member"

    group_openid: Mapped[str] = mapped_column(String(128), primary_key=True)
    member_openid: Mapped[str] = mapped_column(String(128), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(256), default="")
    role: Mapped[str] = mapped_column(String(16), default="member")
    is_bot: Mapped[bool] = mapped_column(Boolean(), default=False)
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    union_openid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, default=None)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
