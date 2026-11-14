from datetime import datetime
from typing import Any, Literal, Optional, Protocol
from typing_extensions import NotRequired, TypedDict

from nonebot_plugin_chat.enums import MoodEnum


class RuaAction(TypedDict):
    name: str
    refusable: bool
    unlock_favorability: float


class CachedMessage(TypedDict):
    content: str
    nickname: str
    user_id: str
    platform_user_id: str
    send_time: datetime
    images: list[bytes]
    self: bool
    message_id: str
    to_me: bool
    triggered_reply: bool
    fake_rich_text: NotRequired[list[str]]  # 消息纯文本中伪装成富文本占位符的片段，用于向模型提示它们是纯文本
    mq_text: NotRequired[
        str
    ]  # 投递到 MessageQueue 的完整文本（含 additional_info），仅在 process_messages 中未阻塞时写入


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


NoteType = Literal["event", "basic_info", "user", "prompt"]

# 记忆类型：
# - event：事件，发生过或即将发生的事、约定、活动、群梗、事实知识等；
# - basic_info：用户基础信息，用户画像里最基础的那部分，每个用户只能有一句话；
# - user：用户画像，中心词必须是用户昵称；
# - prompt：用户对 Moonlark 的指令或要求。
NOTE_TYPES: tuple[NoteType, ...] = ("event", "basic_info", "user", "prompt")


class AvailableNote(TypedDict):
    create: Literal[True]
    type: NoteType
    subject: str
    private: bool
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
