from datetime import datetime
from enum import Enum
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


class AvailableNote(TypedDict):
    create: Literal[True]
    text: str
    expire_days: int
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


class MoodEnum(str, Enum):
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    TRUST = "trust"
    ANTICIPATION = "anticipation"
    CALM = "calm"
    BORED = "bored"
    CONFUSED = "confused"
    TIRED = "tired"
    SHY = "shy"


EMOTIONS = [e.value for e in MoodEnum]