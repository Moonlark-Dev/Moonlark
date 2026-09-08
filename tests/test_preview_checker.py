import asyncio
import socket
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_check_url_protocol_rejects_file() -> None:
    from nonebot_plugin_preview.checker import check_url_protocol
    from nonebot_plugin_preview.exceptions import AccessDenied

    with pytest.raises(AccessDenied):
        check_url_protocol("file:///etc/passwd")


def test_check_url_protocol_http() -> None:
    from nonebot_plugin_preview.checker import check_url_protocol

    assert check_url_protocol("http://example.com/") is True


def test_check_url_protocol_no_scheme() -> None:
    from nonebot_plugin_preview.checker import check_url_protocol

    assert check_url_protocol("example.com") is False


@pytest.mark.asyncio
async def test_check_url_access_blocks_loopback() -> None:
    from nonebot_plugin_preview.checker import check_url_access
    from nonebot_plugin_preview.exceptions import AccessDenied

    with pytest.raises(AccessDenied):
        await check_url_access("http://127.0.0.1:8080/api/bots")


@pytest.mark.asyncio
async def test_check_url_access_blocks_private_ip() -> None:
    from nonebot_plugin_preview.checker import check_url_access
    from nonebot_plugin_preview.exceptions import AccessDenied

    with pytest.raises(AccessDenied):
        await check_url_access("http://192.168.1.1/secret")


@pytest.mark.asyncio
async def test_check_url_access_blocks_data_scheme() -> None:
    from nonebot_plugin_preview.checker import check_url_access
    from nonebot_plugin_preview.exceptions import AccessDenied

    with pytest.raises(AccessDenied):
        await check_url_access("data:text/html,<h1>hi</h1>")


@pytest.mark.asyncio
async def test_check_url_access_blocks_nipio_domain() -> None:
    from nonebot_plugin_preview.checker import check_url_access
    from nonebot_plugin_preview.exceptions import AccessDenied

    loop = asyncio.get_running_loop()
    infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
    with patch.object(loop, "getaddrinfo", new=AsyncMock(return_value=infos)):
        with pytest.raises(AccessDenied):
            await check_url_access("http://127.0.0.1.nip.io:8080/api/bots")


@pytest.mark.asyncio
async def test_check_url_access_allows_public() -> None:
    from nonebot_plugin_preview.checker import check_url_access

    loop = asyncio.get_running_loop()
    infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]
    with patch.object(loop, "getaddrinfo", new=AsyncMock(return_value=infos)):
        await check_url_access("http://example.com/")
