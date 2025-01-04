from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    bots_session_remain: int = 3 * 60
    bots_list: dict[str, str] = {}



config = get_plugin_config(Config)
