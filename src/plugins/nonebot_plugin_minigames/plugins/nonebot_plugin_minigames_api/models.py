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
import math

from nonebot_plugin_orm import Model
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import String
from pydantic import BaseModel


class User(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    total_points: Mapped[int] = mapped_column(default=0)
    exchanged_pawcoin: Mapped[int] = mapped_column(default=0)
    seconds: Mapped[int] = mapped_column(default=0)


class UserData(BaseModel):
    user_id: str
    total_points: int
    exchanged_pawcoin: int
    seconds: int

    def get_exchangeable_pawcoin(self) -> int:
        return int(math.sqrt(self.total_points ** 0.6)) - self.exchanged_pawcoin

