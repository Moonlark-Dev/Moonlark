from pydantic import BaseModel
from nonebot import get_plugin_config

class Config(BaseModel):
    # 热度计算的最大消息速率 (消息数/秒)
    ghot_max_message_rate: float = 10.0

config = get_plugin_config(Config)
