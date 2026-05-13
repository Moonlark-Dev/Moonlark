from nonebot_plugin_items.base.properties import get_properties
from nonebot_plugin_items.base.stack import ItemStack
from nonebot_plugin_items.registry.registry import ResourceLocation
from nonebot_plugin_items.registry import ITEMS
from nonebot_plugin_items.base.gift import GiftItem
from ...lang import lang


class CatCan(GiftItem):

    fav_value: float = 0.00015

    def setupLang(self) -> None:
        self.lang = lang

    async def getDefaultName(self, stack: ItemStack) -> str:
        return await self.getText("gifts.cat_can.name", stack.user_id)

    async def getDescription(self, stack: ItemStack) -> str:
        return await self.getText("gifts.cat_can.description", stack.user_id)


LOCATION = ResourceLocation("moonlark", "cat_can")


def get_location() -> ResourceLocation:
    return LOCATION


ITEMS.registry(LOCATION, CatCan(get_properties(True, 3, 99)))
