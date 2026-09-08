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
    data: int | float
    index: int
    info: Optional[str]
    display: NotRequired[str]


class RankingResponse(TypedDict):
    time: float
    total: int
    title: str
    me: Optional[UserDataWithIndex]
    users: list[UserDataWithIndex]
