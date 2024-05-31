from .lang import lang
from .jrrp import get_luck_value

def get_luck_type(luck_value: int) -> int:
    if luck_value == 100:
        return 1
    elif luck_value == 99:
        return 2
    elif 99 > luck_value >= 85:
        return 3
    elif 85 > luck_value >= 71:
        return 4
    elif 71 > luck_value >= 57:
        return 5
    elif 57 > luck_value >= 43:
        return 6
    elif 43 > luck_value >= 29:
        return 7
    elif 29 > luck_value >= 15:
        return 8
    elif 15 > luck_value >= 1:
        return 9
    else:
        return 10

async def get_luck_message(user_id: str) -> str:
    luck_value = get_luck_value(user_id)
    return await lang.text(
        f"message.msg{get_luck_type(luck_value)}",
        user_id,
        luck_value
    )
