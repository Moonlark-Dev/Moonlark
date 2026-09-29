import httpx

from ..config import config

# 与 nonebot_plugin_openai.utils.client 相同的用法：模块级共享客户端
client = httpx.AsyncClient(
    base_url=config.typesafe_base_url.rstrip("/"),
    timeout=config.typesafe_timeout,
    headers={"User-Agent": "Moonlark/0.1.0 (https://github.com/Moonlark-Dev/Moonlark)"},
)
