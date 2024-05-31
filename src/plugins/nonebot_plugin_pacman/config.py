from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""


from nonebot import get_plugin_config

config = get_plugin_config(Config)
