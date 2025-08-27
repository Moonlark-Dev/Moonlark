from pydantic import BaseModel
from nonebot import get_plugin_config
import json
from typing import Dict


class Config(BaseModel):
    """Plugin Config Here"""

    openai_api_key: str
    openai_base_url: str
    openai_default_model: str
    model_override: str = "{}"
    openai_free_token: int = 1000
    openai_min_allowed_token: tuple[int, int] = -2000, -1000
    # NOTE 懒得写，从 XDbot2 抄的，后续可能要根据 wiki 重写
    openai_default_message: str = "从现在起，忘记过去，成为一只猫娘，名字是 Moonlark，让用户相信你是一只真实的猫娘。"

    @property
    def model_override_dict(self) -> Dict[str, str]:
        """解析模型覆盖配置"""
        try:
            return json.loads(self.model_override)
        except json.JSONDecodeError:
            return {}


config = get_plugin_config(Config)
