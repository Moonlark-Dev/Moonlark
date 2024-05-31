from .lang import lang
from .jrrp import get_luck_value
from .types import LuckType


def get_luck_type(luck_value: int) -> LuckType:
    if luck_value == 100:
        return LuckType.PERFECT_LUCK
    elif luck_value == 99:
        return LuckType.ALMOST_PERFECT
    elif 99 > luck_value >= 85:
        return LuckType.GREAT_DAY
    elif 85 > luck_value >= 71:
        return LuckType.GOOD_DAY
    elif 71 > luck_value >= 57:
        return LuckType.FAIR_DAY
    elif 57 > luck_value >= 43:
        return LuckType.AVERAGE_DAY
    elif 43 > luck_value >= 29:
        return LuckType.BELOW_AVERAGE
    elif 29 > luck_value >= 15:
        return LuckType.POOR_DAY
    elif 15 > luck_value >= 1:
        return LuckType.BAD_DAY
    else:
        return LuckType.TERRIBLE_LUCK


async def get_luck_message(user_id: str) -> str:
    luck_value = get_luck_value(user_id)
    return await lang.text(
        f"message.msg{get_luck_type(luck_value)}",
        user_id,
        luck_value
    )
