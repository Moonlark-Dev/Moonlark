from ..base.stack import ItemStack


def merge_items(items: list[ItemStack]) -> None:
    for i in range(len(items)):
        item = items[-i]
        for j in range(len(items[:i])):
            target = items[j]
            if target.compare(item) and target.isAddable() and item.count > 0:
                count = target.getAddableAmount(item.count)
                target.count += count
                item.count -= count
    for item in items[::-1]:
        if item.count <= 0:
            items.remove(item)
