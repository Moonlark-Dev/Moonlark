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


config = get_plugin_config(Config)
