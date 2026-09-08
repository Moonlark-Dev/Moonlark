# 商品配置：(物品 ID, 单价 / VimCoin)
GOODS: list[tuple[str, int]] = [
    ("moonlark:dried_fish", 20),
    ("moonlark:yarn_ball", 30),
    ("moonlark:bell_collar", 45),
    ("moonlark:catnip_pouch", 45),
    ("moonlark:cat_teaser", 60),
    ("moonlark:cat_can", 90),
    ("moonlark:egg", 15),
    ("moonlark:dice", 30),
]

# 购买时的随机替换表：物品 ID -> [(概率, 替换物品 ID), ...]
# 每个单位独立判定：先按顺序累加概率，命中则获得替换物品，否则获得原物品。
# 例如买鸡蛋时每个鸡蛋有 0.5% 概率变成臭鸡蛋。
GOODS_ALTERNATIVES: dict[str, list[tuple[float, str]]] = {
    "moonlark:egg": [(0.005, "moonlark:rotten_egg")],
}
