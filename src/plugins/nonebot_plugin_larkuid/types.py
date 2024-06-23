from typing import Optional, TypedDict


class LoginResponse(TypedDict):
    session_id: str
    activate_code: str
    effective_time: int


class VerifyResponse(TypedDict):
    user_id: str
    nickname: str

class BasicUserResponse(TypedDict):
    user_id: str
    nickname: str
    level: int
    avatar: Optional[str]

class DetailedUserResponse(BasicUserResponse):
    experience: int
    total_experience: int
    vimcoin: float
    register_time: Optional[float]
    ship_code: Optional[str]
    gender: Optional[int]
    activation_time: float
    health: float
    favorability: float

class EarchTimeData(TypedDict):
    timestamp: float
    strftime: str

class GalacticTimeData(TypedDict):
    strftime: str
    array: list[int]

class TimeResponse(TypedDict):
    earth: EarchTimeData
    galactic: GalacticTimeData