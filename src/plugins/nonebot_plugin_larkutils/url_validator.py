#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import TYPE_CHECKING
from urllib.parse import ParseResult, urlparse

from nonebot.log import logger

if TYPE_CHECKING:
    from playwright.async_api import Request, Route


def _is_internal_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """
    检测单个IP地址是否为内网/本地地址

    Args:
        ip: ipaddress.ip_address() 的返回结果

    Returns:
        bool: True表示是内网/本地IP，False表示是外网IP
    """

    # IPv4私有地址范围
    if isinstance(ip, ipaddress.IPv4Address):
        # 127.0.0.0/8 - 环回地址
        if ip.is_loopback:
            return True
        # 10.0.0.0/8 - A类私有地址
        # 172.16.0.0/12 - B类私有地址
        # 192.168.0.0/16 - C类私有地址
        if ip.is_private:
            return True
        # 169.254.0.0/16 - 链路本地地址
        if ip.is_link_local:
            return True
        # 0.0.0.0/8 - 本网络
        if str(ip).startswith("0."):
            return True

    # IPv6私有地址范围
    elif isinstance(ip, ipaddress.IPv6Address):
        # ::1 - 环回地址
        if ip.is_loopback:
            return True
        # fe80::/10 - 链路本地地址
        if ip.is_link_local:
            return True
        # fc00::/7 - 唯一本地地址
        if ip.is_private:
            return True
        # ::ffff:0:0/96 - IPv4映射地址
        if ip.ipv4_mapped:
            # 递归检查映射的IPv4地址
            return _is_internal_ip(ip.ipv4_mapped)

    return False


def is_internal_url(parsed_url: ParseResult) -> bool:
    """
    检测URL是否指向内网地址、本地资源、data协议或本地环回地址

    Args:
        parsed_url: urllib.parse.urlparse() 的返回结果

    Returns:
        bool: True表示是内网/本地URL，False表示是外网URL
    """

    # 检查协议
    scheme = parsed_url.scheme.lower()

    # data协议直接返回True
    if scheme == "data":
        return True

    # file协议指向本地文件
    if scheme == "file":
        return True

    # 非网络协议的其他本地协议
    if scheme in ["javascript", "vbscript", "about"]:
        return True

    # 获取主机名
    hostname = parsed_url.hostname

    # 如果没有主机名，认为是本地资源
    if not hostname:
        return True

    # 检查是否为IP地址
    try:
        ip = ipaddress.ip_address(hostname)
        return _is_internal_ip(ip)
    except ValueError:
        # 不是IP地址，检查域名
        hostname_lower = hostname.lower()

        # 本地主机名
        if hostname_lower in ["localhost", "localhost.localdomain"]:
            return True

        # .local 域名（mDNS）
        if hostname_lower.endswith(".local"):
            return True

        # .internal 等内部域名
        if hostname_lower.endswith((".internal", ".corp", ".home", ".lan")):
            return True

    return False


async def resolve_internal(parsed_url: ParseResult) -> bool:
    """
    检测URL是否指向内网地址（含 DNS 解析后的结果）

    在 is_internal_url 的基础上，对域名进行 DNS 解析并检查解析出的 IP，
    用于拦截 127.0.0.1.nip.io 这类解析到内网地址的域名（DNS rebinding / SSRF）。

    Args:
        parsed_url: urllib.parse.urlparse() 的返回结果

    Returns:
        bool: True表示是内网/本地URL，False表示是外网URL
    """

    if is_internal_url(parsed_url):
        return True

    hostname = parsed_url.hostname
    if not hostname:
        return True

    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(hostname, None, type=socket.SOCK_STREAM),
            timeout=5,
        )
    except (OSError, asyncio.TimeoutError):
        # 域名无法解析或解析超时时，拒绝访问
        return True

    for _, _, _, _, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if _is_internal_ip(ip):
            return True

    return False


def _is_ip_hostname(hostname: str) -> bool:
    """判断主机名是否为 IP 字面量"""
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True


async def block_internal_request(route: Route, request: Request) -> bool:
    """
    Playwright 路由处理程序：在请求真正发出前拦截指向内网/本地地址的请求。

    用于防止通过 URL 重定向（如 shorturl.com / bitly 短链重定向到 127.0.0.1）绕过 SSRF
    限制。页面导航（含重定向目标）和域名形式的子资源请求做完整的内网检测（含 DNS 解析），
    仅对 IP 字面量的子资源请求走快速字符串级检测，避免无意义的重复 DNS 解析。

    Args:
        route: Playwright 路由对象。
        request: Playwright 请求对象。

    Returns:
        bool: True 表示请求已被拦截（route.abort()），False 表示已放行。
    """

    parsed = urlparse(request.url)
    if request.is_navigation_request() or (parsed.hostname and not _is_ip_hostname(parsed.hostname)):
        blocked = await resolve_internal(parsed)
    else:
        blocked = is_internal_url(parsed)
    try:
        if blocked:
            await route.abort()
        else:
            await route.continue_()
    except Exception as e:
        # 页面可能已关闭或请求已被其他处理器处理，忽略以保持处理器稳定
        logger.debug("无法中止或放行 Playwright 请求: %s", e, exc_info=True)
    return blocked
