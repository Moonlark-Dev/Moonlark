from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """JRRP Plugin Config"""

    jrrp_reroll_max_count: int = 3
    jrrp_reroll_base_cost: int = 60


config = get_plugin_config(Config)
