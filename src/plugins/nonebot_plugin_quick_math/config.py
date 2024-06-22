from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    qm_wait_time: int = 3
    qm_min_limit: int = 3
    qm_retry_count: int = 1
    qm_change_max_level_count: int = 7
    qm_gpt_max_retry: int = 5


config = get_plugin_config(Config)
