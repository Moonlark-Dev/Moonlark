from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    baidu_api_key: str
    baidu_secret_key: str
    superusers: set[str]
    moonlark_api_base: str = "http://localhost:8080"
    image_cache_ttl: int = 600


config = get_plugin_config(Config)
