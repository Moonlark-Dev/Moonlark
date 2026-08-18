from nonebot_plugin_items.base.item import Item
from nonebot_plugin_items.base.properties import get_properties
from nonebot_plugin_items.base.stack import ItemStack
from nonebot_plugin_items.registry.registry import ResourceLocation
from nonebot_plugin_items.registry import ITEMS
from ...lang import lang


class Dice(Item):

    def setupLang(self) -> None:
        self.lang = lang

    async def getDefaultName(self, stack: ItemStack) -> str:
        return await self.getText("dice.name", stack.user_id)


LOCATION = ResourceLocation("moonlark", "dice")


def get_location() -> ResourceLocation:
    return LOCATION


ITEMS.registry(LOCATION, Dice(get_properties(useable=False, star=1, max_stack=64, multi_use=True)))
