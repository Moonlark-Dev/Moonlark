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
from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, Integer, Index, func


class CommandUsage(Model):
    """指令使用记录表"""

    __table_args__ = (
        Index("ix_nonebot_plugin_command_stats_commandusage_used_at_command", "used_at", "command"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    command: Mapped[str] = mapped_column(String(64), index=True)  # 指令名
    user_id: Mapped[str] = mapped_column(String(128), index=True)  # 用户ID
    group_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)  # 群ID（私聊为None）
    used_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)  # 使用时间
