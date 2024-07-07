from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    pawcoin_default_exchange: float = 1.00
    pawcoin_exchange_vars: tuple[float, float, float, float] = (0.05, 100, 0.01, 1000)


config = get_plugin_config(Config)
