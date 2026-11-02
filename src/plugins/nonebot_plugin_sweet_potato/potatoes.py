"""山芋种类注册表。

预留商店联动：以后可以让玩家从商店购买不同种类的山芋并使用，
例如「更容易爆炸的山芋」只需要提供更高的初始概率区间，
游戏逻辑（初始概率、下限、重新抽取）会自动沿用。
"""

from __future__ import annotations

from dataclasses import dataclass

from .logic import INITIAL_PROBABILITY_RANGE


@dataclass(frozen=True)
class PotatoType:
    """一种山芋的属性。

    Attributes:
        id: 山芋种类标识
        name: 展示名称的本地化键
        initial_probability_range: 开局时第一位持有者的爆炸概率区间，也是房间的初始概率下限
    """

    id: str
    name: str
    initial_probability_range: tuple[int, int] = INITIAL_PROBABILITY_RANGE


DEFAULT_POTATO_ID = "default"

POTATO_TYPES: dict[str, PotatoType] = {
    DEFAULT_POTATO_ID: PotatoType(id=DEFAULT_POTATO_ID, name="potato.default"),
}


async def get_active_potato(_user_id: str) -> PotatoType:
    """获取玩家当前使用的山芋种类。

    目前所有玩家都使用默认山芋；商店联动功能预留在这里：
    读取玩家购买的 / 装备的山芋物品，并返回对应的 :class:`PotatoType`。
    """
    return POTATO_TYPES[DEFAULT_POTATO_ID]
