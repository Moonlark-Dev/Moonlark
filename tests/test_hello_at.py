"""``/hello``（@Bot 空正文）回复逻辑的回归测试。

背景（PR #1601 的 E2E 报告「发现 3」）：``nonebot_plugin_hello/main.py`` 里
``if is_chat_enabled(event, session_id):`` 少了一个 ``await``。``enabled_group`` 是协程，
判断条件拿到的是恒为真的协程对象，于是处理器每次都在第一行返回，``/hello`` 永远不回复
（同时留下 ``coroutine was never awaited`` 警告）。

这里直接调用插件注册的处理器：chat 未启用时必须继续往下走，chat 已启用或正文非空时
必须提前返回。
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


class _StopError(Exception):
    """在真正读写用户数据之前中断处理器，让用例只验证前置判断"""


def _get_at_handler() -> Callable[..., Any]:
    from nonebot import get_plugin

    plugin = get_plugin("nonebot_plugin_hello")
    assert plugin is not None, "nonebot_plugin_hello 未加载"
    matcher = next(iter(plugin.matcher))
    # handlers[0] 是 nonebot 包装过的 Dependent，取 .call 才是插件里那个协程函数
    return matcher.handlers[0].call


@pytest.mark.asyncio
async def test_at_replies_when_chat_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """chat 未启用的群里 @Bot，处理器应继续执行（即会回复问候语）"""
    from nonebot_plugin_hello import main as hello

    chat_enabled = AsyncMock(return_value=False)
    schedule = AsyncMock(side_effect=_StopError)
    monkeypatch.setattr(hello, "is_chat_enabled", chat_enabled)
    monkeypatch.setattr(hello, "complete_schedule", schedule)

    event = MagicMock()
    event.get_plaintext.return_value = ""

    with pytest.raises(_StopError):
        await _get_at_handler()(event, "10000", "qq_20000")

    chat_enabled.assert_awaited_once_with(event, "qq_20000")
    schedule.assert_awaited_once_with("10000", "at")


@pytest.mark.asyncio
async def test_at_skips_when_chat_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """chat 已启用的群里由 chat 插件回应，hello 不重复回复"""
    from nonebot_plugin_hello import main as hello

    chat_enabled = AsyncMock(return_value=True)
    schedule = AsyncMock()
    monkeypatch.setattr(hello, "is_chat_enabled", chat_enabled)
    monkeypatch.setattr(hello, "complete_schedule", schedule)

    event = MagicMock()
    event.get_plaintext.return_value = ""

    await _get_at_handler()(event, "10000", "qq_20000")

    chat_enabled.assert_awaited_once_with(event, "qq_20000")
    schedule.assert_not_awaited()


@pytest.mark.asyncio
async def test_at_skips_when_message_has_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """@Bot 但正文非空时走 chat 路径，hello 不处理"""
    from nonebot_plugin_hello import main as hello

    chat_enabled = AsyncMock(return_value=False)
    schedule = AsyncMock()
    monkeypatch.setattr(hello, "is_chat_enabled", chat_enabled)
    monkeypatch.setattr(hello, "complete_schedule", schedule)

    event = MagicMock()
    event.get_plaintext.return_value = "在吗"

    await _get_at_handler()(event, "10000", "qq_20000")

    chat_enabled.assert_not_awaited()
    schedule.assert_not_awaited()
