from ..base.stack import ItemStack


def merge_items(items: list[ItemStack]) -> None:
    for i in range(len(items)):
        item = items[-i]
        for j in range(len(items[:i])):
            target = items[j]
            if target.compare(item) and target.count < target.item.getProperties()["max_stack"] and item.count > 0:
                target.count += (reduced := min(target.item.getProperties()["max_stack"] - target.count, item.count))
                item.count -= reduced
    for item in items[::-1]:
        if item.count <= 0:
            items.remove(item)
