"""合成机配方与升级配置。"""

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class Recipe:
    """一个配方：投入若干物品与 VimCoin，经过固定时长得到产物。

    Attributes:
        id: 配方标识
        inputs: 需要投入的物品（物品 ID -> 数量）
        vimcoin: 需要支付的 VimCoin
        duration: 合成耗时
        output_id: 产物物品 ID
        output_count: 产物数量
    """

    id: str
    inputs: dict[str, int]
    vimcoin: int
    duration: timedelta
    output_id: str
    output_count: int = 1


# 配方注册表：配方 id -> 配方
RECIPES: dict[str, Recipe] = {}

# 合成机等级 -> 可同时进行的合成数量（物品数）
LEVEL_SLOTS: dict[int, int] = {1: 2, 2: 4, 3: 6, 4: 10}
# 升级到该等级需要的 VimCoin（从 level-1 升到 level）
UPGRADE_COSTS: dict[int, int] = {2: 300, 3: 900, 4: 2500}

MAX_LEVEL = max(LEVEL_SLOTS)


def register_recipe(recipe: Recipe) -> Recipe:
    RECIPES[recipe.id] = recipe
    return recipe


register_recipe(
    Recipe(
        id="rotten_egg",
        inputs={"moonlark:egg": 1},
        vimcoin=10,
        duration=timedelta(hours=6),
        output_id="moonlark:rotten_egg",
    ),
)
register_recipe(
    Recipe(
        id="rotten_egg_ex",
        inputs={"moonlark:rotten_egg": 1},
        vimcoin=20,
        duration=timedelta(hours=3),
        output_id="moonlark:rotten_egg_ex",
    ),
)
register_recipe(
    Recipe(
        id="cake",
        inputs={"moonlark:egg": 5, "moonlark:milk": 3},
        vimcoin=100,
        duration=timedelta(hours=24),
        output_id="moonlark:cake",
    ),
)
