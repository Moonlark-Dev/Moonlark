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

import io
from urllib.parse import urljoin, urlparse

import httpx
from nonebot import logger
from PIL import Image, UnidentifiedImageError

from nonebot_plugin_larkutils.url_validator import resolve_internal

# 允许下载的单张图片最大体积
MAX_IMAGE_SIZE = 10 * 1024 * 1024
# 允许的最大重定向次数
MAX_REDIRECTS = 3
# 单张图片允许的最大像素数（防御解压缩炸弹）
MAX_IMAGE_PIXELS = 40_000_000
# 下载超时时间（秒）
REQUEST_TIMEOUT = 15.0
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "image/*,*/*;q=0.8",
}

# 可以直接透传给模型的图片格式，其余格式统一转换为 JPEG
_FORMAT_TO_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}


class ImageDownloadError(Exception):
    """图片下载失败，异常信息可以直接返回给模型"""


async def _fetch_image(url: str) -> bytes:
    """下载 URL 内容

    会校验每一跳地址（含重定向目标）是否指向内网，并限制下载体积。

    Args:
        url: 图片 URL

    Returns:
        bytes: 图片二进制数据
    """
    current_url = url
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            parsed = urlparse(current_url)
            if parsed.scheme not in ("http", "https"):
                raise ImageDownloadError("仅支持 http/https 链接")
            if await resolve_internal(parsed):
                raise ImageDownloadError("不允许访问内网地址")
            async with client.stream("GET", current_url, headers=REQUEST_HEADERS) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ImageDownloadError("重定向响应缺少 Location")
                    current_url = urljoin(str(response.url), location)
                    continue
                if response.status_code != 200:
                    raise ImageDownloadError(f"请求失败 (HTTP {response.status_code})")
                content_length = response.headers.get("content-length")
                if content_length and content_length.isdigit() and int(content_length) > MAX_IMAGE_SIZE:
                    raise ImageDownloadError("图片体积超过 10 MB")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_IMAGE_SIZE:
                        raise ImageDownloadError("图片体积超过 10 MB")
                    chunks.append(chunk)
                return b"".join(chunks)
    raise ImageDownloadError("重定向次数过多")


def _check_image_pixels(image: Image.Image) -> None:
    """校验图片像素规模，防御解压缩炸弹

    Args:
        image: 已打开的 Pillow 图片对象
    """
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise ImageDownloadError("图片尺寸过大")


def _normalize_image(data: bytes) -> tuple[bytes, str]:
    """校验图片内容并识别 MIME 类型

    Pillow 无法直接输出的格式会转换为 JPEG，避免把非图片数据塞进上下文。

    Args:
        data: 下载得到的二进制数据

    Returns:
        tuple[bytes, str]: (图片数据, MIME 类型)
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            _check_image_pixels(image)
            image_format = (image.format or "").upper()
            mime_type = _FORMAT_TO_MIME.get(image_format)
            if mime_type is not None:
                image.load()
                return data, mime_type
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="JPEG", quality=90)
            return buffer.getvalue(), "image/jpeg"
    except ImageDownloadError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as e:
        raise ImageDownloadError("链接内容不是可识别的图片") from e


async def download_image(url: str) -> tuple[bytes, str]:
    """从 URL 下载图片

    Args:
        url: 图片 URL

    Returns:
        tuple[bytes, str]: (图片数据, MIME 类型)

    Raises:
        ImageDownloadError: 下载失败、内容不是图片或体积超限
    """
    data = await _fetch_image(url)
    if not data:
        raise ImageDownloadError("图片内容为空")
    image, mime_type = _normalize_image(data)
    logger.debug(f"request_image 已下载图片: {url} -> {mime_type}, {len(image)} bytes")
    return image, mime_type
