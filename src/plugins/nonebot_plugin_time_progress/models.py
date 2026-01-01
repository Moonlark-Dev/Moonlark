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
from sqlalchemy import String, Boolean, Integer


class TimeProgressSubscription(Model):
    """群聊年进度推送订阅设置"""

    group_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sent_year: Mapped[int] = mapped_column(Integer, default=0)
    last_sent_percentage: Mapped[int] = mapped_column(Integer, default=0)