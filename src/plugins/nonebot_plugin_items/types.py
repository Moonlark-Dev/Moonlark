from typing import Any
from typing_extensions import TypedDict


class DictItemData(TypedDict):
    item_id: str
    count: int
    data: dict[str, Any]
