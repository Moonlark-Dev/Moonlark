from nonebot_plugin_items.base.item import Item
from nonebot_plugin_items.base.properties import get_properties
from nonebot_plugin_items.base.stack import ItemStack
from nonebot_plugin_items.registry import ITEMS
from nonebot_plugin_items.registry.registry import ResourceLocation
from ...lang import lang


class Egg(Item):
    def setupLang(self) -> None:
        self.lang = lang

    async def getDefaultName(self, stack: ItemStack) -> str:
        return await self.getText("egg.name", stack.user_id)


LOCATION = ResourceLocation("moonlark", "egg")


def get_location() -> ResourceLocation:
    return LOCATION


ITEMS.registry(LOCATION, Egg(get_properties(False, 1, 999)))
