from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    cave_maximum_similarity: float = 0.75


config = get_plugin_config(Config)
