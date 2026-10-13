#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

from datetime import datetime
from typing import Optional

from nonebot_plugin_orm import Model
from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class QQGroupInfo(Model):
    """QQ 官方 Bot 群聊缓存（群基本信息 + 群成员同步状态）

    ``group_openid`` 由 QQ 开放平台按应用分配，同一个群在不同 Bot（不同 AppID）
    下会有不同的 openid，因此这里把发现该群的 Bot 一并记录下来。
    """

    __tablename__ = "nonebot_plugin_qq_group_info"

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

    __tablename__ = "nonebot_plugin_qq_group_member"

    group_openid: Mapped[str] = mapped_column(String(128), primary_key=True)
    member_openid: Mapped[str] = mapped_column(String(128), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(256), default="")
    role: Mapped[str] = mapped_column(String(16), default="member")
    is_bot: Mapped[bool] = mapped_column(Boolean(), default=False)
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    union_openid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, default=None)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
