from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    command_start: list[str]
    session_retention_days: int = 3
    unused_session_remove_delay: int = 300
    cors_allow_origins: list[str] = ["*"]


config = get_plugin_config(Config)
