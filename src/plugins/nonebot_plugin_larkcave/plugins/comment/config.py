from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    cave_message_list_length: int = 20


config = get_plugin_config(Config)
