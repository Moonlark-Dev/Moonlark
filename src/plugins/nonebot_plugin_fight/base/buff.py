#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
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
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from . import Monomer
from ..types import BuffData
from abc import ABC, abstractmethod


class Buff(ABC):

    def __init__(self, data: BuffData, monomer: "Monomer") -> None:
        self.data = data
        self.monomer = monomer

    @abstractmethod
    async def setup(self) -> None:
        pass

    @abstractmethod
    async def remove(self) -> None:
        pass

    @abstractmethod
    async def action(self) -> None:
        pass

    async def pop(self) -> None:
        index = self.monomer.buff_list.index(self)
        if index >= 0:
            self.monomer.buff_list.pop(index)
        await self.remove()

    def __getitem__(self, item: Literal["buff_type", "remain_rounds", "data"]):
        return self.data[item]

    def __setitem__(self, key: Literal["buff_type", "remain_rounds", "data"], value):
        self.data[key] = value
