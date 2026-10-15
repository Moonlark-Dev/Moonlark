from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """nonebot_plugin_updates Config"""

    superusers: list[str] = []


config = get_plugin_config(Config)
