from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    baidu_api_key: str
    baidu_secret_key: str
    superusers: set[str]
    command_start: list[str]


config = get_plugin_config(Config)
