from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """nonebot_plugin_broadcast Config

    - ``superusers``：复用全局超管。公告发布与广播 HTTP 接口的 Web 会话鉴权都看它；
    - ``broadcast_api_tokens``：广播 HTTP 接口的机器凭据，``{名称: token}``。
      名称只用于审计与限流（写进 ``BroadcastRecord.submitter`` 的是 ``api:名称``），
      留空表示不开放机器凭据，只接受超管 Web 会话；
    - ``broadcast_api_rate_limit`` / ``broadcast_api_rate_window``：每个调用方在
      时间窗口内允许触发的广播次数（进程内滑动窗口，<=0 表示不限流）；
    - ``broadcast_api_max_content_length``：单次广播正文的最大字符数。
    """

    superusers: list[str] = []
    broadcast_api_tokens: dict[str, str] = {}
    broadcast_api_rate_limit: int = 5
    broadcast_api_rate_window: float = 60.0
    broadcast_api_max_content_length: int = 5000


config = get_plugin_config(Config)
