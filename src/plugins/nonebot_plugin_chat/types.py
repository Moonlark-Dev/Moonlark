from datetime import datetime
from typing import Any, Literal, Optional, Protocol, TypedDict

from nonebot_plugin_chat.enums import MoodEnum


class RuaAction(TypedDict):
    name: str
    refusable: bool
    unlock_favorability: float


class CachedMessage(TypedDict):
    content: str
    nickname: str
    user_id: str
    send_time: datetime
    images: list[bytes]
    self: bool
    message_id: str


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
    message_id: str  # 触发交互的消息 ID，用于 reaction


class AvailableNote(TypedDict):
    create: Literal[True]
    text: str
    expire_hours: float
    keywords: Optional[str]
    comment: str


class InvalidNote(TypedDict):
    create: Literal[False]
    comment: str


NoteCheckResult = AvailableNote | InvalidNote


class AdapterUserInfo(TypedDict):
    sex: Literal["male", "female", "unknown"]
    role: Literal["member", "admin", "owner", "user"]
    nickname: str
    join_time: int
    card: Optional[str]


EMOTIONS = [e.value for e in MoodEnum]
