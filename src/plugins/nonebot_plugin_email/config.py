from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""
    superusers: list[str] = []
    email_expired_days: int = 30


config = get_plugin_config(Config)
