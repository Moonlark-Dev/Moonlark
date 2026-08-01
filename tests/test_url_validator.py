import asyncio
import socket
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

import pytest

INTERNAL_URLS = [
    # 本地协议
    "data:text/plain;base64,SGVsbG8=",
    "file:///etc/passwd",
    "javascript:alert(1)",
    "vbscript:msgbox(1)",
    "about:blank",
    # 无主机名
    "mailto:user@example.com",
    # 本地主机名
    "http://localhost/",
    "http://localhost.localdomain/",
    # 内部域名后缀
    "http://example.local/",
    "http://intranet.internal/",
    "http://corp.example.corp/",
    "http://router.home/",
    "http://nas.lan/",
    # IPv4 环回/私有/链路本地/本网络
    "http://127.0.0.1/",
    "http://127.0.1.1:8080/",
    "http://10.0.0.1/",
    "http://172.16.0.1/",
    "http://172.31.255.255/",
    "http://192.168.1.1/",
    "http://169.254.169.254/",
    "http://0.0.0.0/",
    "http://0.42.42.42/",
    # IPv6 环回/链路本地/唯一本地/IPv4映射
    "http://[::1]/",
    "http://[fe80::1]/",
    "http://[fc00::1]/",
    "http://[::ffff:127.0.0.1]/",
    "http://[::ffff:10.0.0.1]/",
]

EXTERNAL_URLS = [
    "http://8.8.8.8/",
    "http://1.1.1.1/",
    "http://172.32.0.1/",
    "http://192.169.1.1/",
    "http://11.0.0.1/",
    "http://example.com/",
    "https://www.google.com/path?q=1",
    "http://[2001:4860:4860::8888]/",
    # nip.io 域名字符串级无法识别，需依赖 DNS 解析（resolve_internal）
    "http://127.0.0.1.nip.io:8080/api/bots",
]


def _infos(*ips: str) -> list[tuple]:
    """构造 getaddrinfo 返回值的简化形式 (family, type, proto, canonname, sockaddr)"""
    result = []
    for ip in ips:
        if ":" in ip:
            result.append((socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, 0, 0, 0)))
        else:
            result.append((socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 80)))
    return result


@pytest.mark.parametrize("url", INTERNAL_URLS)
def test_is_internal_url_true(url: str) -> None:
    from nonebot_plugin_larkutils.url_validator import is_internal_url

    assert is_internal_url(urlparse(url)) is True


@pytest.mark.parametrize("url", EXTERNAL_URLS)
def test_is_internal_url_false(url: str) -> None:
    from nonebot_plugin_larkutils.url_validator import is_internal_url

    assert is_internal_url(urlparse(url)) is False


@pytest.mark.asyncio
async def test_resolve_internal_blocks_nipio_loopback() -> None:
    from nonebot_plugin_larkutils.url_validator import resolve_internal

    loop = asyncio.get_running_loop()
    with patch.object(loop, "getaddrinfo", new=AsyncMock(return_value=_infos("127.0.0.1"))):
        assert await resolve_internal(urlparse("http://127.0.0.1.nip.io:8080/api/bots")) is True


@pytest.mark.asyncio
async def test_resolve_internal_blocks_nipio_private() -> None:
    from nonebot_plugin_larkutils.url_validator import resolve_internal

    loop = asyncio.get_running_loop()
    with patch.object(loop, "getaddrinfo", new=AsyncMock(return_value=_infos("10.0.0.1"))):
        assert await resolve_internal(urlparse("http://10.0.0.1.nip.io:8080/")) is True


@pytest.mark.asyncio
async def test_resolve_internal_allows_public_domain() -> None:
    from nonebot_plugin_larkutils.url_validator import resolve_internal

    loop = asyncio.get_running_loop()
    with patch.object(loop, "getaddrinfo", new=AsyncMock(return_value=_infos("93.184.216.34"))):
        assert await resolve_internal(urlparse("http://example.com/")) is False


@pytest.mark.asyncio
async def test_resolve_internal_blocks_when_any_ip_internal() -> None:
    from nonebot_plugin_larkutils.url_validator import resolve_internal

    loop = asyncio.get_running_loop()
    with patch.object(loop, "getaddrinfo", new=AsyncMock(return_value=_infos("93.184.216.34", "192.168.1.1"))):
        assert await resolve_internal(urlparse("http://example.com/")) is True


@pytest.mark.asyncio
async def test_resolve_internal_blocks_dns_failure() -> None:
    from nonebot_plugin_larkutils.url_validator import resolve_internal

    loop = asyncio.get_running_loop()
    with patch.object(loop, "getaddrinfo", new=AsyncMock(side_effect=OSError("resolve failed"))):
        assert await resolve_internal(urlparse("http://unknown.invalid/")) is True


@pytest.mark.asyncio
async def test_resolve_internal_blocks_ipv6_internal() -> None:
    from nonebot_plugin_larkutils.url_validator import resolve_internal

    loop = asyncio.get_running_loop()
    with patch.object(loop, "getaddrinfo", new=AsyncMock(return_value=_infos("::1"))):
        assert await resolve_internal(urlparse("http://ipv6.example.com/")) is True


@pytest.mark.asyncio
async def test_resolve_internal_short_circuits_without_dns() -> None:
    from nonebot_plugin_larkutils.url_validator import resolve_internal

    loop = asyncio.get_running_loop()
    mock_ga = AsyncMock(return_value=_infos("93.184.216.34"))
    with patch.object(loop, "getaddrinfo", new=mock_ga):
        assert await resolve_internal(urlparse("http://127.0.0.1:8080/")) is True
    mock_ga.assert_not_awaited()
