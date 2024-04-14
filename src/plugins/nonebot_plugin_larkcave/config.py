from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""
    cave_need_review: bool = False
    cave_user_cd: float = 10

config = get_plugin_config(Config)