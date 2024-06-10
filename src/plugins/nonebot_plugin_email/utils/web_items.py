import json
from ..types import EmailItemData


def parse_items(items: str) -> list[EmailItemData]:
    item_list = []
    for item in items.splitlines():
        d = item.split("|", 2)
        if len(d) == 1:
            d.extend(["1", "{}"])
        item_list.append({
            "item_id": d[0],
            "count": int(d[1]),
            "data": json.loads(d[2]),
        })
    return item_list
