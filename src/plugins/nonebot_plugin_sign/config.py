from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    hitokoto_api: str = "https://v1.hitokoto.cn/"
    command_start: list[str]
    moonlark_api_base: str


config = get_plugin_config(Config)
