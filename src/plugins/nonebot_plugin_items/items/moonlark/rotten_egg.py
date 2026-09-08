from nonebot_plugin_items.base.item import Item
from nonebot_plugin_items.base.properties import get_properties
from nonebot_plugin_items.base.stack import ItemStack
from nonebot_plugin_items.registry import ITEMS
from nonebot_plugin_items.registry.registry import ResourceLocation
from ...lang import lang


class RottenEgg(Item):
    def setupLang(self) -> None:
        self.lang = lang

    async def getDefaultName(self, stack: ItemStack) -> str:
        return await self.getText("rotten_egg.name", stack.user_id)


LOCATION = ResourceLocation("moonlark", "rotten_egg")


def get_location() -> ResourceLocation:
    return LOCATION


ITEMS.registry(LOCATION, RottenEgg(get_properties(False, 1, 999)))
