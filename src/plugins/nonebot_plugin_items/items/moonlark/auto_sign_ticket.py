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
from nonebot_plugin_items.base.item import Item
from nonebot_plugin_items.base.properties import get_properties
from nonebot_plugin_items.base.stack import ItemStack
from nonebot_plugin_items.registry.registry import ResourceLocation
from nonebot_plugin_items.registry import ITEMS
from ...lang import lang


class AutoSignTicket(Item):
    def setupLang(self) -> None:
        self.lang = lang

    async def getDefaultName(self, stack: ItemStack) -> str:
        return await self.getText("auto_sign_ticket.name", stack.user_id)

    async def getDescription(self, stack: ItemStack) -> str:
        return await self.getText("auto_sign_ticket.description", stack.user_id)


LOCATION = ResourceLocation("moonlark", "auto_sign_ticket")


def get_location() -> ResourceLocation:
    return LOCATION


ITEMS.registry(LOCATION, AutoSignTicket(get_properties(useable=False, star=3, max_stack=99, multi_use=True)))
