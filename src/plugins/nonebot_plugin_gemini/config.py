from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    """Plugin Config Here"""

    # Gemini API Key（不配置时插件仍可加载，只是真正调用模型时会报错）
    gemini_api_key: str = ""
    # Gemini API 地址，留空使用 SDK 默认的官方地址；使用 AxonHub 等网关时填网关地址
    gemini_base_url: str = ""
    # API 版本（留空由 SDK 决定，通常为 v1）；网关只提供 v1beta 时填写 v1beta
    gemini_api_version: str = ""
    gemini_default_model: str = "gemini-2.5-flash"
    identify_prefix: str = "Moonlark"
    gemini_thread_header: str = "AH-Thread-Id"
    # 支持配置多个 Trace Id 请求头，全部携带相同的 trace_id 值
    gemini_trace_headers: list[str] = ["AH-Trace-Id"]
    # 使用 use_default_message 时插入的 system 消息（留空表示不插入）
    gemini_default_message: str = ""
    # 图片被安全策略拦截后，替换为文字描述并重试的最大次数
    gemini_image_block_retries: int = 2
    # reasoning_effort -> Gemini thinking 配置。默认留空，表示不向模型传递任何 thinking 配置，
    # 由模型自己决定是否思考（不同模型对 thinking_budget / thinking_level 的支持并不一致，
    # 设错会让请求直接失败，因此需要按实际使用的模型显式配置）。
    # Gemini 3 及以后使用 gemini_thinking_levels（如 {"low": "LOW", "medium": "HIGH"}），
    # 更早的模型使用 gemini_thinking_budgets（如 {"low": 1024, "medium": 8192}）。
    gemini_thinking_levels: dict[str, str] = {}
    gemini_thinking_budgets: dict[str, int] = {}


config = get_plugin_config(Config)
