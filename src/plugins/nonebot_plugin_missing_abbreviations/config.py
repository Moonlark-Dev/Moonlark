from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """“缩略” 的玩法参数。"""

    missing_abbreviations_model: str = "google/gemini-4-hydrogen"
    missing_abbreviations_generate_count: int = 20
    missing_abbreviations_generate_timeout: int = 180
    missing_abbreviations_cache_low_water: int = 5
    missing_abbreviations_max_attempts: int = 10
    missing_abbreviations_idle_timeout: int = 180
    missing_abbreviations_reward: float = 3.0
    missing_abbreviations_history_size: int = 80


config = get_plugin_config(Config)
