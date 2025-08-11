from typing import Any

from nonebot_plugin_larkuser import get_user
from nonebot import logger
from nonebot_plugin_items.base.properties import ItemProperties, get_properties
from nonebot_plugin_items.base.stack import ItemStack
from nonebot_plugin_items.registry.registry import ResourceLocation
from nonebot_plugin_items.registry import ITEMS
import random
from nonebot_plugin_items.base.useable import UseableItem
from ...lang import lang


def get_result(c: int, is_data=False):
    if is_data:
        return c
    if 193 <= c <= 200:  # 20
        return 20
    elif 183 <= c <= 192:  # 18-19
        return random.randint(18, 19)
    elif 153 <= c <= 182:  # 15-17
        return random.randint(15, 17)
    elif 106 <= c <= 152:  # 10-14
        return random.randint(10, 14)
    elif 16 <= c <= 105:  # 2-9
        return random.randint(2, 9)
    elif c <= 15:  # 1
        return 1
    return 0


async def single_use(stack: "ItemStack") -> tuple[int, int]:
    c = get_result(random.randint(0, 200))
    user = await get_user(stack.user_id)
    if c == 20:
        await user.add_vimcoin(50)
        return c, 50
    elif 18 <= c <= 19:
        await user.add_vimcoin(20)
        return c, 20
    elif 15 <= c <= 17:
        await user.add_vimcoin(10)
        return c, 10
    elif 10 <= c <= 14:
        await user.add_vimcoin(5)
        return c, 5
    elif c == 1:  # 1
        await user.use_vimcoin(50, True)
        return c, -50
    return c, 0


class Dice(UseableItem):

    async def useItem(self, stack: "ItemStack", *args, **kwargs) -> str:
        if "count" in kwargs:
            count = kwargs["count"]
        else:
            count = 1
        if count == 1:
            num, vim = await single_use(stack)
            return await self.lang.text(f"dice.result_single.l_{vim}", stack.user_id, num)
        else:
            num = 0
            vim = 0
            for _ in range(count):
                result = await single_use(stack)
                num += result[0]
                vim += result[1]
            num //= count
            if num >= 14:
                type_id = 1
            elif num <= 6:
                type_id = 2
            else:
                type_id = 3
            return await self.lang.text(
                "dice.result_multi.main",
                stack.user_id,
                count,
                await self.lang.text(f"dice.result_multi._{type_id}", stack.user_id),
                vim
            )


    def setupLang(self) -> None:
        self.lang = lang

    async def getDefaultName(self, stack: ItemStack) -> str:
        return await self.getText("dice.name", stack.user_id)




LOCATION = ResourceLocation("moonlark", "dice")


def get_location() -> ResourceLocation:
    return LOCATION


ITEMS.registry(LOCATION, Dice(get_properties(False, 1, 64)))
