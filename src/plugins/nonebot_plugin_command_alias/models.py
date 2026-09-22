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
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column


class CommandAlias(Model):
    """用户指令别名表

    每个用户（主账号）可以为常用指令设置一个自定义别名，
    发送 ``/别名`` 时会自动改写为对应的原指令。
    """

    __tablename__ = "nonebot_plugin_command_alias"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)  # 用户ID（主账号）
    alias: Mapped[str] = mapped_column(String(64), primary_key=True)  # 自定义别名
    command: Mapped[str] = mapped_column(String(64))  # 原指令名
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())  # 创建时间
