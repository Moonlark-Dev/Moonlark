from pydantic import BaseModel
from nonebot import get_plugin_config

config = get_plugin_config(Config)


class Config(BaseModel):
    """Plugin Config Here"""

    bot_assign_effective_time: int = 5 * 60


config = get_plugin_config(Config)
