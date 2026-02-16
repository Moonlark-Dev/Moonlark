from datetime import datetime
from typing import Any, Literal, Optional, Protocol, TypedDict

from nonebot_plugin_chat.models import RuaAction


class RuaAction(TypedDict):
    name: str
    refusable: bool
    unlock_favorability: float


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


class GetTextFunc(Protocol):
    # 在这里精确模拟你的函数签名
    async def __call__(self, key: str, *args: Any, **kwargs: Any) -> str: ...


class PendingInteraction(TypedDict):
    """待处理的交互请求"""

    interaction_id: str
    user_id: str
    nickname: str
    action: RuaAction
    created_at: float  # timestamp
