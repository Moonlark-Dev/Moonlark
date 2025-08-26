from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    status_report_password: str = "Moonlark"


config = get_plugin_config(Config)
