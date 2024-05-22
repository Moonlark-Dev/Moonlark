from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    hitokoto_api: str = "https://v1.hitokoto.cn/"


config = get_plugin_config(Config)
