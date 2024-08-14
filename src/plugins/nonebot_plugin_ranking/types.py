from typing import Optional
from typing_extensions import TypedDict


class RankingData(TypedDict):
    user_id: str
    data: int | float
    info: str | None


class UserDataWithIndex(TypedDict):
    user_id: str
    nickname: str
    data: int | float
    index: int
    info: str | None


class RankingResponse(TypedDict):
    time: float
    total: int
    title: str
    me: Optional[UserDataWithIndex]
    users: list[UserDataWithIndex]
