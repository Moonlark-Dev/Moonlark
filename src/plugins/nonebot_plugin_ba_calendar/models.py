#  Moonlark - A new ChatBot
#  Copyright (C) 2024  Moonlark Development Team
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

from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, BigInteger


class BacReminderSubscription(Model):
    """群聊提醒订阅设置"""
    group_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    server: Mapped[str] = mapped_column(String(2), default="cn")  # cn, in, jp


class BacReminderSent(Model):
    """已发送的提醒记录，防止重复发送"""
    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True)
    activity_id: Mapped[int] = mapped_column(BigInteger)
    reminder_type: Mapped[str] = mapped_column(String(16))  # start, end
    server: Mapped[str] = mapped_column(String(2))  # cn, in, jp