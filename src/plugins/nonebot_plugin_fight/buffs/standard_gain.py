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

from ..base import Buff, Monomer
from ..types import BuffData



class StandardGain(Buff):

    def __init__(self, data: BuffData, monomer: Monomer) -> None:
        super().__init__(data, monomer)
        self.attr = data["data"]["attr"]
        self.value = data["data"]["value"]

    async def setup(self) -> None:
        value = getattr(self.monomer, self.attr) + self.value
        setattr(self.monomer, self.attr, value)

    async def remove(self) -> None:
        value = getattr(self.monomer, self.attr) - self.value
        setattr(self.monomer, self.attr, value)

    async def action(self) -> None:
        pass



class StandardPercentGain(Buff):

    def __init__(self, data: BuffData, monomer: Monomer) -> None:
        super().__init__(data, monomer)
        self.attr = data["data"]["attr"]
        self.value = 0
        self.percent = data["data"]["percent"]


    async def setup(self) -> None:
        value = getattr(self.monomer, self.attr) * self.percent
        self.value = value - getattr(self.monomer, self.attr)
        setattr(self.monomer, self.attr, value)

    async def remove(self) -> None:
        value = getattr(self.monomer, self.attr) - self.value
        setattr(self.monomer, self.attr, value)

    async def action(self) -> None:
        pass
