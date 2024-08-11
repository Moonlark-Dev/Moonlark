from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""
    bingo_max_prompt_count: int = 49


config = get_plugin_config(Config)
