"""Gemini 客户端

客户端按需创建：插件在未配置 ``GEMINI_API_KEY`` 时也能正常加载（其它插件可能只是
``require`` 它而没有真正调用），直到第一次请求模型时才抛出
:class:`~nonebot_plugin_gemini.exceptions.GeminiNotConfigured`。
"""

from typing import Optional

from google import genai
from google.genai import types

from ..config import config
from ..exceptions import GeminiNotConfigured

_client: Optional[genai.Client] = None


def get_client() -> genai.Client:
    """获取（并缓存）Gemini 客户端"""
    global _client
    if _client is None:
        if not config.gemini_api_key:
            raise GeminiNotConfigured("未配置 GEMINI_API_KEY，无法请求 Gemini 模型")
        _client = genai.Client(
            api_key=config.gemini_api_key,
            http_options=types.HttpOptions(
                base_url=config.gemini_base_url or None,
                api_version=config.gemini_api_version or None,
            ),
        )
    return _client


def reset_client() -> None:
    """丢弃缓存的客户端（配置变更或测试时使用）"""
    global _client
    _client = None
