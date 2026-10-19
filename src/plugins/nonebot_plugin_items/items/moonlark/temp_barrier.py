from nonebot_plugin_items.base.item import Item
from nonebot_plugin_items.base.properties import get_properties
from nonebot_plugin_items.base.stack import ItemStack
from nonebot_plugin_items.registry import ITEMS
from nonebot_plugin_items.registry.registry import ResourceLocation
from ...lang import lang


class TempBarrier(Item):
    """临时屏障：装备后可阻挡 20 次 splat 攻击，被击中时有 2% 概率反弹攻击者。"""

    usage_command = "equip"

    def setupLang(self) -> None:
        self.lang = lang

    async def getDefaultName(self, stack: ItemStack) -> str:
        return await self.getText("temp_barrier.name", stack.user_id)


LOCATION = ResourceLocation("moonlark", "temp_barrier")


def get_location() -> ResourceLocation:
    return LOCATION


ITEMS.registry(LOCATION, TempBarrier(get_properties(False, 3, 8)))
