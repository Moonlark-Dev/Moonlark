from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""
    bag_max_size: int = 32
    overflow_protect_hours: int = 2


config = get_plugin_config(Config)
