from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    command_start: list[str]
    # 登录时未激活会话的初始有效期（天）；前端「记住我」可通过 retention_days 请求参数延长
    session_retention_days: int = 3
    # 未激活会话保留时长（秒），超时由定时任务清理
    unused_session_remove_delay: int = 300
    login_pending_max_wait: int = 25
    cors_allow_origins: list[str] = ["*"]
    # 滑动过期：激活后的会话每次活跃都向后顺延 expiration_time，空闲超过该天数即失效
    session_idle_days: int = 7
    # 会话绝对寿命上限（自创建起算），无论多活跃到期必须重新登录；存量无创建时间的会话不受限
    session_max_lifetime_days: int = 30
    # 每用户并发会话上限，登录时超出则挤掉最早的会话
    max_sessions_per_user: int = 5
    # /api/login 限流（滑动窗口）：窗口秒数内每 IP+UA 最多 times 次
    login_rate_limit_times: int = 10
    login_rate_limit_window_seconds: int = 60


config = get_plugin_config(Config)
