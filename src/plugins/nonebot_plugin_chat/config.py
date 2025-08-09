from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    command_start: list[str] = ["/"]


config = get_plugin_config(Config)
