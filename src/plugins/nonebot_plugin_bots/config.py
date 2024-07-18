from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    bots_session_clear_time: str = "*"


config = get_plugin_config(Config)
