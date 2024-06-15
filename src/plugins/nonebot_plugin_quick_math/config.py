from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""
    qm_wait_time: int = 5
    qm_retry_count: int = 3
    qm_change_max_level_count: int = 10

config = get_plugin_config(Config)
