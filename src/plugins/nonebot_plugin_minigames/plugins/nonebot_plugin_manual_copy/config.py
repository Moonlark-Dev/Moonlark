from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    manual_copy_api: str = "https://v1.hitokoto.cn/?c=i&c=d&min_length=10"


config = get_plugin_config(Config)
