from datetime import datetime
from typing import Literal, TypedDict


class RuaAction(TypedDict):
    name: str
    refusable: bool
    unlock_favorability: float


class PendingInteraction(TypedDict):
    """待处理的交互请求"""

    interaction_id: str
    user_id: str
    nickname: str
    action: RuaAction
    created_at: float  # timestamp


class CachedMessage(TypedDict):
    content: str
    nickname: str
    user_id: str
    send_time: datetime
    self: bool
    message_id: str


class AdapterUserInfo(TypedDict):
    sex: Literal["male", "female", "unknown"]
    role: Literal["member", "admin", "owner", "user"]
    nickname: str
    join_time: int
    card: Optional[str]