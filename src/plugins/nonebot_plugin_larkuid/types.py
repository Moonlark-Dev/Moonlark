from typing import Optional
from typing_extensions import NotRequired, TypedDict
from typing_extensions import TypedDict as TypedDictExtension


class LoginResponse(TypedDictExtension):
    session_id: str
    activate_code: str
    effective_time: int
    command_prefix: str


class LoginPendingResponse(TypedDictExtension):
    activated: bool
    # 激活时后端会轮换会话 ID（防 fixation），前端需用它替换本地存储的旧 ID
    session_id: NotRequired[str]


class SessionInfo(TypedDictExtension):
    """设备管理列表项；时间为 UTC epoch 秒。"""

    session_id: str
    current: bool
    device: Optional[str]
    created_at: Optional[float]
    last_active_at: Optional[float]
    expires_at: Optional[float]


class VerifyResponse(TypedDictExtension):
    user_id: str
    nickname: str


class MessageResponse(TypedDictExtension):
    success: bool
    message: str


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
