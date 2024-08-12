from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    tol_default_size: tuple[int, int] = 9, 9


config = get_plugin_config(Config)
