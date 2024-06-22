from ....nonebot_plugin_item.base.stack import ItemStack
from ....nonebot_plugin_item.registry.registry import ResourceLocation
from ....nonebot_plugin_item.registry import ITEMS
from ....nonebot_plugin_item.base.item import Item
from ...lang import lang


class Vimcoin(Item):

    def setupLang(self) -> None:
        self.lang = lang

    async def getDefaultName(self, stack: ItemStack) -> str:
        return await self.getText("vimcoin.name", stack.user_id)


ITEMS.registry(ResourceLocation("special", "vimcoin"), Vimcoin({"max_stack": 0xFFFF, "star": 3, "useable": False}))
