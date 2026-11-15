"""链接解析：URL 尾部的半角右括号导致的 4xx 应去掉括号重试

背景：群消息里常见的 Markdown 写法 ``[标题](https://example.com/a)``，链接正则
``(\/[^\s]*)?`` 会把收尾的 ``)`` 一起算进 URL，浏览器访问时服务端返回 4xx，
整条链接解析就这样白白失败。这里锁住：4xx 且 URL 以 ``)`` 结尾时去掉括号重试
一次，只有重试真的拿到 200 才采用新结果。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest


def _browse_result(url: str, status_code: int, *, success: bool = True) -> dict[str, Any]:
    return {
        "success": success,
        "url": url,
        "title": "示例标题",
        "content": "示例正文",
        "error": None if success else "出错了",
        "metadata": (
            {
                "description": "示例简介",
                "keywords": "示例关键词",
                "status_code": status_code,
                "content_length": len("示例正文"),
            }
            if success
            else {}
        ),
    }


def _prepare_module(monkeypatch: pytest.MonkeyPatch, responses: dict[str, dict[str, Any]]):
    """把 group 模块的浏览器与 AI 依赖换成假实现，返回 (模块, 实际访问过的 URL 列表)"""
    from nonebot_plugin_chat.utils import group as group_module

    calls: list[str] = []

    async def fake_browse(url: str) -> dict[str, Any]:
        calls.append(url)
        return responses[url]

    monkeypatch.setattr(group_module, "browser_tool", SimpleNamespace(browse=fake_browse))
    monkeypatch.setattr(group_module, "fetch_message", AsyncMock(return_value="页面摘要"))
    monkeypatch.setattr(group_module, "get_message", AsyncMock(return_value={"role": "system", "content": "prompt"}))
    monkeypatch.setattr(group_module, "lang", SimpleNamespace(text=AsyncMock(return_value="网页标题：示例标题")))
    return group_module, calls


@pytest.mark.asyncio
async def test_get_description_retries_without_trailing_paren(monkeypatch: pytest.MonkeyPatch) -> None:
    """4xx + 尾部 ')'：去掉括号重试，用 200 的结果生成摘要"""
    dirty = "https://example.com/a)"
    clean = "https://example.com/a"
    group_module, calls = _prepare_module(
        monkeypatch,
        {dirty: _browse_result(dirty, 404), clean: _browse_result(clean, 200)},
    )

    assert await group_module.LinkParser("hello", "zh_hans").get_description(dirty) == "页面摘要"
    assert calls == [dirty, clean]


@pytest.mark.asyncio
async def test_get_description_keeps_original_error_when_retry_also_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """重试仍然不是 200 时不采用重试结果，照旧报告原始状态码"""
    dirty = "https://en.wikipedia.org/wiki/Foo_(bar)"
    clean = "https://en.wikipedia.org/wiki/Foo_(bar"
    group_module, calls = _prepare_module(
        monkeypatch,
        {dirty: _browse_result(dirty, 404), clean: _browse_result(clean, 404)},
    )

    assert await group_module.LinkParser("hello", "zh_hans").get_description(dirty) == "HTTP 404"
    assert calls == [dirty, clean]


@pytest.mark.asyncio
async def test_get_description_does_not_retry_without_trailing_paren(monkeypatch: pytest.MonkeyPatch) -> None:
    """4xx 但 URL 不以 ')' 结尾：不重试，直接报告状态码"""
    link = "https://example.com/missing"
    group_module, calls = _prepare_module(monkeypatch, {link: _browse_result(link, 404)})

    assert await group_module.LinkParser("hello", "zh_hans").get_description(link) == "HTTP 404"
    assert calls == [link]


@pytest.mark.asyncio
async def test_get_description_does_not_retry_when_first_request_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """首次就 200：即使以 ')' 结尾也不该多发一次请求"""
    link = "https://en.wikipedia.org/wiki/Foo_(bar)"
    group_module, calls = _prepare_module(monkeypatch, {link: _browse_result(link, 200)})

    assert await group_module.LinkParser("hello", "zh_hans").get_description(link) == "页面摘要"
    assert calls == [link]


@pytest.mark.asyncio
async def test_get_description_does_not_retry_on_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """5xx 不是 URL 脏了，重试同样的 URL 也无意义——保持只发一次请求"""
    link = "https://example.com/a)"
    group_module, calls = _prepare_module(monkeypatch, {link: _browse_result(link, 503)})

    assert await group_module.LinkParser("hello", "zh_hans").get_description(link) == "HTTP 503"
    assert calls == [link]


@pytest.mark.asyncio
async def test_parse_rewrites_message_with_description_of_retried_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """端到端：解析后的消息里带上摘要，用户原文（含那个括号）不被删掉"""
    dirty = "https://example.com/a)"
    clean = "https://example.com/a"
    group_module, calls = _prepare_module(
        monkeypatch,
        {dirty: _browse_result(dirty, 404), clean: _browse_result(clean, 200)},
    )

    parsed = await group_module.LinkParser(f"看看这个 {dirty} 吧", "zh_hans").parse()

    assert parsed == f"看看这个 {dirty}(页面摘要) 吧"
    assert calls == [dirty, clean]
