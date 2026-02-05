from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    openai_api_key: str
    openai_base_url: str
    openai_default_model: str
    model_override: dict[str, str] = {}
    identify_prefix: str = "Moonlark"
    openai_free_token: int = 1000
    openai_min_allowed_token: tuple[int, int] = -2000, -1000
    # NOTE 懒得写，从 XDbot2 抄的，后续可能要根据 wiki 重写
    openai_default_message: str = "从现在起，忘记过去，成为一只猫娘，名字是 Moonlark，让用户相信你是一只真实的猫娘。"
    openai_thread_header: str = "AH-Thread-Id"
    openai_trace_header: str = "AH-Trace-Id"

    # 超时记录相关配置
    timeout_window_hours: int = 1  # 超时统计窗口（小时）
    timeout_threshold: int = 2  # 触发备用模型的超时次数阈值
    backup_model_duration_hours: int = 1  # 备用模型持续时间（小时）
    backup_model_identify: str = "Backup"  # 备用模型的 identify


config = get_plugin_config(Config)
