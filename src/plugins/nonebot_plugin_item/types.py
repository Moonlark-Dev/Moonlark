from typing import Any, TypedDict


class DictItemData(TypedDict):
    item_id: str
    count: int
    data: dict[str, Any]
