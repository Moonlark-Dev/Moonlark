from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    vote_remain_hour: int = 2


config = get_plugin_config(Config)
