from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""
    unlock_experience: int = 15


config = get_plugin_config(Config)
