from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""
    access_fallback: bool = True


config = get_plugin_config(Config)
