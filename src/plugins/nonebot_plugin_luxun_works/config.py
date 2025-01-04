from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    luxun_min_diff: float = 0.75


config = get_plugin_config(Config)
