# 商店商品分类配置：分类标识 -> [(物品 ID, 单价 / VimCoin), ...]
# 分类标识用于展示（shop.yaml 的 category.* 键），购买仍使用跨分类的统一编号。
GOODS_CATEGORIES: dict[str, list[tuple[str, int]]] = {
    "gift": [
        ("moonlark:dried_fish", 20),
        ("moonlark:yarn_ball", 30),
        ("moonlark:bell_collar", 45),
        ("moonlark:catnip_pouch", 45),
        ("moonlark:cat_teaser", 60),
        ("moonlark:cat_can", 90),
        ("moonlark:egg", 15),
        ("moonlark:dice", 30),
    ],
    "consumable": [
        ("moonlark:milk", 35),
    ],
    "equipment": [
        ("moonlark:temp_barrier", 150),
    ],
}

# 商城的完整商品列表（按分类展开后的统一购买顺序）
GOODS: list[tuple[str, int]] = [goods for items in GOODS_CATEGORIES.values() for goods in items]

# 购买时的随机替换表：物品 ID -> [(概率, 替换物品 ID), ...]
# 每个单位独立判定：先按顺序累加概率，命中则获得替换物品，否则获得原物品。
# 例如买鸡蛋时每个鸡蛋有 0.5% 概率变成臭鸡蛋。
GOODS_ALTERNATIVES: dict[str, list[tuple[float, str]]] = {
    "moonlark:egg": [(0.005, "moonlark:rotten_egg")],
}
