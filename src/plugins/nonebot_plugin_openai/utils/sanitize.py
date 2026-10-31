"""清理发往模型接口的请求体

网关（如 AxonHub）会把请求体原样写进 PostgreSQL 的 ``jsonb`` 列，而 ``jsonb`` 不接受
JSON 里的 ``\\u0000`` 转义（U+0000 / NUL）：请求体任意字符串里只要混进一个 NUL，
整次请求的请求体就会落库失败，网关只想保留一条记录时便用 ``{"message": "invalid text"}``
占位，从外部看起来就像 Moonlark 发了一条只有这个请求体的请求。

聊天文本、群名片、工具返回（远程命令输出、网页正文等）都可能带 NUL，而 NUL 在对话内容
里没有意义，因此在构造请求前统一剔除。清理函数只返回副本，不改动调用方持有的消息列表：
chat context 依靠消息内容与请求列表一致来做前缀对齐，就地改写会让两边错位。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# JSON 里必须转义、而 PostgreSQL jsonb 又拒收的字符
NUL = "\x00"


def strip_nul(value: Any) -> Any:
    """递归剔除字符串里的 U+0000

    非字符串的叶子节点（数字、布尔、None 等）原样返回；pydantic 模型按 OpenAI SDK
    发请求时的序列化方式先转成 dict 再清理，避免模型响应里的对象带着 NUL 进入请求体。

    Args:
        value: 任意嵌套的请求数据（消息列表、工具定义等）

    Returns:
        Any: 清理后的副本；没有 NUL 时字符串仍是原对象
    """
    if isinstance(value, str):
        return value.replace(NUL, "") if NUL in value else value
    if isinstance(value, list):
        return [strip_nul(item) for item in value]
    if isinstance(value, tuple):
        return tuple(strip_nul(item) for item in value)
    if isinstance(value, dict):
        return {strip_nul(key) if isinstance(key, str) else key: strip_nul(item) for key, item in value.items()}
    if isinstance(value, BaseModel):
        return strip_nul(value.model_dump(mode="json", exclude_unset=True))
    return value
