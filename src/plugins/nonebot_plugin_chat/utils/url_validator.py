#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
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

import ipaddress
from urllib.parse import ParseResult


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
                ipv4_mapped = ip.ipv4_mapped
                if ipv4_mapped.is_private or ipv4_mapped.is_loopback or ipv4_mapped.is_link_local:
                    return True

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
