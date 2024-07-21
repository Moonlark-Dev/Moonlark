from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""
    moonlark_api_base: str


config = get_plugin_config(Config)
