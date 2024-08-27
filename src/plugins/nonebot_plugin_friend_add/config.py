from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    friend_add_award_fav: float = 0.05


config = get_plugin_config(Config)
