from typing import Optional, TypedDict
from typing_extensions import TypedDict as TypedDictExtension


class LoginResponse(TypedDictExtension):
    session_id: str
    activate_code: str
    effective_time: int


class VerifyResponse(TypedDictExtension):
    user_id: str
    nickname: str


class BasicUserResponse(TypedDictExtension):
    user_id: str
    nickname: str
    level: int
    avatar: Optional[str]


class DetailedUserResponse(BasicUserResponse):
    experience: int
    total_experience: int
    vimcoin: float
    register_time: Optional[float]
    health: float
    favorability: float


class EarchTimeData(TypedDictExtension):
    timestamp: float
    strftime: str


class GalacticTimeData(TypedDictExtension):
    strftime: str
    array: list[int]


class TimeResponse(TypedDictExtension):
    earth: EarchTimeData
    galactic: GalacticTimeData
