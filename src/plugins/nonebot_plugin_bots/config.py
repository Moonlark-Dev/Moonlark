from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    bots_session_remain: int = 3 * 60
    bots_list: dict[str, str] = {}

    # app_id -> QQ 号的映射表，用于识别 QQ 官方 bot 的自发自收消息
    # 例如: {"102xxxxxx": "3889000000"}
    bots_appid_map: dict[str, str] = {}

    # 群绑定验证码过期时间（秒），默认 5 分钟
    bots_bind_group_timeout: int = 300

    # 共享群中 OneBot 11 可用性检查的缓存时间（秒），默认 5 分钟
    # 控制 get_group_list 的重算频率，值越大对 OneBot 11 接口的调用越少，但状态变更生效越慢
    bots_ob11_availability_ttl: int = 300


config = get_plugin_config(Config)
