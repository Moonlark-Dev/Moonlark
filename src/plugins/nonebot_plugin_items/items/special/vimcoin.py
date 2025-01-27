from nonebot_plugin_items.base.properties import ItemProperties, get_properties
from nonebot_plugin_items.base.stack import ItemStack
from nonebot_plugin_items.registry.registry import ResourceLocation
from nonebot_plugin_items.registry import ITEMS
from nonebot_plugin_items.base.item import Item
from ...lang import lang


class Vimcoin(Item):

    def setupLang(self) -> None:
        self.lang = lang

    async def getDefaultName(self, stack: ItemStack) -> str:
        return await self.getText("vimcoin.name", stack.user_id)


LOCATION = ResourceLocation("special", "vimcoin")


def get_location() -> ResourceLocation:
    return LOCATION


ITEMS.registry(LOCATION, Vimcoin(get_properties(False, 3, 0xFFF)))
