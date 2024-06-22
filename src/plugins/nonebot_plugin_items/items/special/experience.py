from ....nonebot_plugin_item.base.stack import ItemStack
from ....nonebot_plugin_item.registry.registry import ResourceLocation
from ....nonebot_plugin_item.registry import ITEMS
from ....nonebot_plugin_item.base.item import Item
from ...lang import lang


class Experience(Item):

    def setupLang(self) -> None:
        self.lang = lang

    async def getDefaultName(self, stack: ItemStack) -> str:
        return await self.getText("experience.name", stack.user_id)


LOCATION = ResourceLocation("special", "experience")


def get_location() -> ResourceLocation:
    return LOCATION


ITEMS.registry(LOCATION, Experience({"max_stack": 0xFFFFF, "star": 2, "useable": False}))
