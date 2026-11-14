from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    bingo_max_prompt_count: int = 49
    # 等待输入的超时时间（秒）
    bingo_input_timeout: int = 300


config = get_plugin_config(Config)
