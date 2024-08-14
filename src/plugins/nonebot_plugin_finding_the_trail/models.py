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
from sqlalchemy import String
from sqlalchemy.orm import mapped_column, Mapped


class UserPoint(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    points: Mapped[int] = mapped_column(default=0)
    count: Mapped[int] = mapped_column(default=0)
    exchanged: Mapped[int] = mapped_column(default=0)