from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    tol_default_size: tuple[int, int] = 9, 9
    # 等待输入的超时时间（秒）
    tol_input_timeout: int = 300


config = get_plugin_config(Config)
