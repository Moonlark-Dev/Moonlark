from datetime import datetime
from typing import Any, TypedDict


class EmailItemData(TypedDict):
    item_id: str
    count: int
    data: dict[str, Any]


class EmailData(TypedDict):
    id: int
    author: str
    content: str
    subject: str
    time: datetime
    items: list[EmailItemData]
    is_read: bool
    is_claimed: bool
