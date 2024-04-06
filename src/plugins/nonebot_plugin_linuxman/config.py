from pydantic import BaseModel
from nonebot import get_plugin_config

class Config(BaseModel):
    """Plugin Config Here"""
    linuxman_url: str = "https://man.archlinux.org/man/"

config = get_plugin_config(Config)