from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    # OpenRouter Decisions API 配置，见 https://openrouter.ai/docs/guides/features/decisions
    decision_api_key: str = ""
    decision_base_url: str = "https://openrouter.ai/api/alpha"
    decision_model: str = "google/gemini-decision-1"
    decision_timeout: float = 15.0
    # 单次请求失败后的重试次数（不含首次；仅对网络异常、408、429 及 5xx 重试）
    decision_max_retries: int = 2


config = get_plugin_config(Config)
