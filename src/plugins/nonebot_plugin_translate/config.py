from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
    translate_deeplx_url: str 

from nonebot import get_plugin_config
config = get_plugin_config(Config)