"""Moonlark 内置 buff 定义。

这些 buff 同时被多个插件读取（签到 / 商店 / 人品 / 掷骰等），因此统一定义
在这里，避免插件之间互相依赖。
"""

from datetime import timedelta

from .api import attach_buff, get_buff_layers
from .registry import BuffDefinition, register_buff

# 霉运：被臭鸡蛋砸中后附着，期间各类收益与运气都会被削弱
BAD_LUCK_BUFF_ID = "moonlark:bad_luck"
# 每一层霉运的持续时间
BAD_LUCK_DURATION = timedelta(hours=2)
# 最多叠加到 3 层
BAD_LUCK_MAX_LAYERS = 3

BAD_LUCK = register_buff(
    BuffDefinition(
        id=BAD_LUCK_BUFF_ID,
        name_key="builtin.bad_luck.name",
        description_key="builtin.bad_luck.description",
        max_layers=BAD_LUCK_MAX_LAYERS,
        default_duration=BAD_LUCK_DURATION,
    ),
)


def bad_luck_multiplier(layers: int) -> float:
    """每多一层霉运，收益与触发概率减半"""
    return 0.5 ** max(int(layers), 0)


async def attach_bad_luck(user_id: str, layers: int = 1) -> None:
    """给用户附着霉运 buff（可叠加，每层 2 小时）"""
    await attach_buff(user_id, BAD_LUCK_BUFF_ID, layers=layers)


async def get_bad_luck_layers(user_id: str) -> int:
    """获取用户当前的霉运层数，没有霉运时返回 0"""
    return await get_buff_layers(user_id, BAD_LUCK_BUFF_ID)


async def get_bad_luck_multiplier(user_id: str) -> float:
    """获取用户当前的霉运收益系数（无霉运时为 1.0）"""
    return bad_luck_multiplier(await get_bad_luck_layers(user_id))
