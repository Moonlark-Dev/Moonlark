from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    command_start: list[str] = ["/"]
    google_api_key: str
    google_search_engine_id: str


config = get_plugin_config(Config)
