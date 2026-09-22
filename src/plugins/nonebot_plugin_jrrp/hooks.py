"""人品值相关的 buff 效果。

带有「霉运」buff 时抽取或重抽人品值会更容易得到低分，甚至直接跌到 0。
这里通过 larkutils 的 `register_luck_value_hook` 钩子接入，避免
larkutils 反向依赖 buff 插件。
"""

import random

from nonebot_plugin_buff.builtin import bad_luck_multiplier, get_bad_luck_layers
from nonebot_plugin_larkutils.jrrp import register_luck_value_hook

# 每层霉运额外增加直接抽到 0 的概率
BAD_LUCK_ZERO_CHANCE_PER_LAYER = 0.15


async def apply_bad_luck_to_luck(user_id: str, value: int) -> int:
    """霉运压制人品值：先按层数折减（每层减半），再按层数概率直接归零"""
    layers = await get_bad_luck_layers(user_id)
    if layers <= 0:
        return value
    if random.random() < BAD_LUCK_ZERO_CHANCE_PER_LAYER * layers:  # nosec B311
        return 0
    return max(int(value * bad_luck_multiplier(layers)), 0)


register_luck_value_hook(apply_bad_luck_to_luck)
