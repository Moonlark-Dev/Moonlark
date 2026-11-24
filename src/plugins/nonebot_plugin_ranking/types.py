from typing import Optional
from typing_extensions import NotRequired, TypedDict


class RankingData(TypedDict):
    user_id: str
    data: int | float
    info: Optional[str]
    display: NotRequired[str]


class UserDataWithIndex(TypedDict):
    user_id: str
    nickname: str
    # Web 端优先展示 display，因此 data 可能是格式化后的字符串（如 "+50.00%"）
    data: int | float | str
    index: int
    info: Optional[str]
    display: NotRequired[str]


class RankingResponse(TypedDict):
    time: float
    total: int
    title: str
    me: Optional[UserDataWithIndex]
    users: list[UserDataWithIndex]
