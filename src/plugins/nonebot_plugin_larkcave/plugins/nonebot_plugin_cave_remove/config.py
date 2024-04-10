from pydantic import BaseModel
from nonebot import get_plugin_config

class Config(BaseModel):
    """Plugin Config Here"""
    cave_restore_date: int = 7

config = get_plugin_config(Config)
