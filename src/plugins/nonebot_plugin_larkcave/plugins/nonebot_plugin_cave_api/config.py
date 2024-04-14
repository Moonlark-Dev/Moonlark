from pydantic import BaseModel
from nonebot import get_plugin_config

class Config(BaseModel):
    """Plugin Config Here"""
    cave_api_base_url: str = "http://127.0.0.1:8080"

config = get_plugin_config(Config)