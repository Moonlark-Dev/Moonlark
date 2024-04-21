from pydantic import BaseModel
from nonebot import get_plugin_config

class Config(BaseModel):
    """Plugin Config Here"""
    vote_remain_hour: int = 2


config = get_plugin_config(Config)