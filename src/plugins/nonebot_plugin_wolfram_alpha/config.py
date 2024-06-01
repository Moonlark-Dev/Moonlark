from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    wolfram_api_key: str


config = get_plugin_config(Config)
