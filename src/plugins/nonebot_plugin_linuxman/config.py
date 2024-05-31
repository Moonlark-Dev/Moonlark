from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    linuxman_url: str = "https://man.archlinux.org/man/"


config = get_plugin_config(Config)
