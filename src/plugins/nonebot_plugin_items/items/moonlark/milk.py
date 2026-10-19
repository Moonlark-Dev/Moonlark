from nonebot_plugin_items.base.consumable import ConsumableItem
from nonebot_plugin_items.base.properties import get_properties
from nonebot_plugin_items.base.stack import ItemStack
from nonebot_plugin_items.registry import ITEMS
from nonebot_plugin_items.registry.registry import ResourceLocation
from ...lang import lang


class Milk(ConsumableItem):
    """牛奶：消耗品，喝下后有 90% 概率消除一个负面 buff（多层只消除一层）。"""

    usage_command = "consumables"

    # 喝下后生效的概率（霉运 buff 会按层数降低该概率）
    SUCCESS_PROBABILITY = 0.9

    def setupLang(self) -> None:
        self.lang = lang

    async def getDefaultName(self, stack: ItemStack) -> str:
        return await self.getText("milk.name", stack.user_id)

    async def on_use(self, stack: ItemStack) -> str | None:
        from random import random  # nosec B311

        from nonebot_plugin_buff import get_bad_luck_multiplier
        from nonebot_plugin_buff.api import detach_random_negative_buff, get_buff_name

        if random() >= self.SUCCESS_PROBABILITY * await get_bad_luck_multiplier(stack.user_id):  # nosec B311
            return await self.getText("milk.use_none", stack.user_id)
        attachment = await detach_random_negative_buff(stack.user_id)
        if attachment is None:
            return await self.getText("milk.use_none", stack.user_id)
        name = await get_buff_name(attachment, stack.user_id)
        return await self.getText("milk.use_success", stack.user_id, name)


LOCATION = ResourceLocation("moonlark", "milk")


def get_location() -> ResourceLocation:
    return LOCATION


ITEMS.registry(LOCATION, Milk(get_properties(useable=True, star=1, max_stack=64)))
