from typing import Optional

from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    setu_cd: int = 20
    setu_cache_count: int = 10
    setu_proxy: Optional[str] = None
    setu_retry_time: int = 3


config = get_plugin_config(Config)
