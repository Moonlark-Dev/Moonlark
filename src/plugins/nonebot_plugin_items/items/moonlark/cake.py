from nonebot_plugin_items.base.consumable import ConsumableItem
from nonebot_plugin_items.base.gift import GiftItem
from nonebot_plugin_items.base.properties import get_properties
from nonebot_plugin_items.base.stack import ItemStack
from nonebot_plugin_items.registry import ITEMS
from nonebot_plugin_items.registry.registry import ResourceLocation
from ...lang import lang


class Cake(GiftItem, ConsumableItem):
    """蛋糕：可以送给 Moonlark（每天最多一个，display_fav +3），也可以自己吃掉回满血。"""

    fav_value: float = 0.003
    daily_gift_limit: int = 1

    usage_command = "consumables"

    def setupLang(self) -> None:
        self.lang = lang

    async def getDefaultName(self, stack: ItemStack) -> str:
        return await self.getText("cake.name", stack.user_id)

    async def on_gift_used(self, stack: ItemStack, **kwargs) -> None:
        pass

    async def on_use(self, stack: ItemStack) -> str | None:
        from nonebot_plugin_larkuser import get_user
        from nonebot_plugin_larkuser.user.base import MAX_HEALTH

        user = await get_user(stack.user_id)
        if not user.is_registered():
            return await self.getText("cake.use_unregistered", stack.user_id)
        before = user.get_health()
        if before >= MAX_HEALTH:
            return await self.getText("cake.use_full", stack.user_id)
        await user.set_health(MAX_HEALTH)
        return await self.getText("cake.use_heal", stack.user_id, round(MAX_HEALTH - before, 1))


LOCATION = ResourceLocation("moonlark", "cake")


def get_location() -> ResourceLocation:
    return LOCATION


ITEMS.registry(LOCATION, Cake(get_properties(useable=True, star=3, max_stack=64)))
