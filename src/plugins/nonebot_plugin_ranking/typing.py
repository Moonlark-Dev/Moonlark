from typing import TypedDict


class RankingData(TypedDict):
    user_id: str
    data: int | float
    info: str | None


class UserDataWithIndex(TypedDict):
    nickname: str
    data: int | float
    index: int
    info: str | None


class UserData(TypedDict):
    nickname: str
    data: int | float
    info: str | None


class WebUserData(TypedDict):
    nickname: str
    data: int | float
    info: str | None
    user_id: str