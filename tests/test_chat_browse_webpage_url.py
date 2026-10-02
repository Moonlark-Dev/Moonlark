"""`browse_webpage` 的 URL 规范化与错误分类回归测试

背景（生产事故）：模型调用 `browse_webpage` 抓取一个正常的公网 Bing 搜索页，
却收到 `# 访问失败 / 无法访问本地资源`。根因有两条：

1. `AsyncBrowserTool.browse` 先 `urlparse(url)` 再校验，最后才补 `https://`。
   于是 "www.bing.com/search?q=x" 这种没有协议串的 URL 在 `urlparse` 下
   hostname 为空，被 `is_internal_url` 判成「无主机名的本地资源」而直接拒绝。
2. `resolve_internal` 在 DNS 解析失败/超时时返回 `True`（与「内网」同义），
   于是任何一次临时 DNS 抖动都会让正常的公网站点被报成「本地资源」。

这里锁住：先补协议再校验、DNS 失败给出区别于「本地资源」的错误文案。
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

BING_URL = "https://www.bing.com/search?q=%E6%B5%8B%E8%AF%95"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://example.com/a", "https://example.com/a"),
        ("http://example.com/a", "http://example.com/a"),
        # 没有协议：必须补上 https://（补完 hostname 才非空）
        ("example.com/a", "https://example.com/a"),
        ("www.bing.com/search?q=x", "https://www.bing.com/search?q=x"),
        # 模型常把 URL 包在空白/尖括号里
        ("  https://example.com/a  ", "https://example.com/a"),
        ("<https://example.com/a>", "https://example.com/a"),
        # 「主机:端口」写法：urlparse 会把主机名当成 scheme，必须仍然补 https://
        ("example.com:8080/a", "https://example.com:8080/a"),
        ("www.bing.com:443/search?q=x", "https://www.bing.com:443/search?q=x"),
    ],
)
def test_normalize_url_adds_scheme_before_validation(raw: str, expected: str) -> None:
    from nonebot_plugin_chat.utils.tools.browser import _normalize_url

    assert _normalize_url(raw) == expected


def test_normalize_url_then_validates_as_external() -> None:
    """补协议后，无协议的公网 URL 不能再被判定为本地资源"""

    from urllib.parse import urlparse

    from nonebot_plugin_chat.utils.tools.browser import _normalize_url
    from nonebot_plugin_larkutils.url_validator import is_internal_url

    # 未规范化时会被误判（这正是事故成因，锁住它避免回退）
    assert is_internal_url(urlparse("www.bing.com/search?q=x")) is True
    # 规范化后必须是外部 URL
    normalized = _normalize_url("www.bing.com/search?q=x")
    assert is_internal_url(urlparse(normalized)) is False


@pytest.mark.asyncio
async def test_browse_reports_dns_failure_not_local_resource() -> None:
    """DNS 解析失败时，错误文案不能是「无法访问本地资源」"""

    from nonebot_plugin_chat.utils.tools.browser import browser_tool

    loop = asyncio.get_running_loop()
    with patch.object(loop, "getaddrinfo", new=AsyncMock(side_effect=OSError("Temporary failure in name resolution"))):
        result = await browser_tool.browse(BING_URL)

    assert result["success"] is False
    assert "本地资源" not in result["error"]
    assert "解析" in result["error"]


@pytest.mark.asyncio
async def test_browse_still_blocks_real_internal_urls() -> None:
    """修复错误分类不能削弱 SSRF 防护：真正的内网地址仍须被拒"""

    from nonebot_plugin_chat.utils.tools.browser import browser_tool

    for url in ("http://127.0.0.1:8080/api/bots", "http://localhost/", "http://192.168.1.1/"):
        result = await browser_tool.browse(url)
        assert result["success"] is False, url
        assert result["error"] == "无法访问本地资源", url


@pytest.mark.asyncio
async def test_browse_localhost_without_scheme_still_blocked() -> None:
    """补协议不应把真正的内网目标放过去"""

    from nonebot_plugin_chat.utils.tools.browser import browser_tool

    result = await browser_tool.browse("localhost:8080/api/bots")
    assert result["success"] is False
    assert result["error"] == "无法访问本地资源"
