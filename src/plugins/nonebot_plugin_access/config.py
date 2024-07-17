from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    access_fallback: bool = True


config = get_plugin_config(Config)
