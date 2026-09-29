from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    # TypeSafe Jev (System One) API，见 https://docs.typesafe.ai
    typesafe_api_key: str = ""
    typesafe_base_url: str = "https://api.typesafe.ai/v1"
    typesafe_model: str = "jev-latest"
    typesafe_timeout: float = 15.0
    # 单次请求失败后的重试次数（不含首次）
    typesafe_max_retries: int = 2


config = get_plugin_config(Config)
