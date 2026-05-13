from nonebot_plugin_items.base.properties import get_properties
from nonebot_plugin_items.base.stack import ItemStack
from nonebot_plugin_items.registry.registry import ResourceLocation
from nonebot_plugin_items.registry import ITEMS
from nonebot_plugin_items.base.gift import GiftItem
from ....lang import lang


class CatTeaser(GiftItem):

    fav_value: float = 0.00015

    def setupLang(self) -> None:
        self.lang = lang

    async def getDefaultName(self, stack: ItemStack) -> str:
        return await self.getText("gifts.cat_teaser.name", stack.user_id)

    async def getDescription(self, stack: ItemStack) -> str:
        return await self.getText("gifts.cat_teaser.description", stack.user_id)

    async def on_gift_used(self, stack, *args, **kwargs):
        pass


LOCATION = ResourceLocation("moonlark", "cat_teaser")


def get_location() -> ResourceLocation:
    return LOCATION


ITEMS.registry(LOCATION, CatTeaser(get_properties(True, 3, 99)))
