from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    user_registered_guest: bool = False

config = get_plugin_config(Config)