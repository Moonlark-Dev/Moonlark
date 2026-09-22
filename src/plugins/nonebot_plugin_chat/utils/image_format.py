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
"""图片格式校验与归一化

模型的图片输入接口只接受 webp / png / jpeg / gif 四种格式，其余格式
（bmp、tiff、ico、heic 等）或损坏的二进制数据都会导致上游返回
``invalid_request_error`` 并中断整轮对话。本模块负责在任何图片进入模型
上下文之前统一完成校验与转换：

- 已受支持的格式：原样保留，并返回真实 MIME 类型（不再一律谎报 jpeg）；
- Pillow 能解码但模型不支持的格式：转换为 JPEG，带透明通道时转换为 PNG；
- 无法解码 / 体积与像素超限：抛出 :class:`ImageFormatError`，由调用方决定
  是跳过还是返回提示，避免污染对话上下文。
"""

from __future__ import annotations

import base64
import io
from typing import Any, Optional

from PIL import Image, UnidentifiedImageError

# 模型图片输入接口支持的 MIME 类型
SUPPORTED_IMAGE_MIME_TYPES: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})

# Pillow 识别出的格式名 -> 可直接透传给模型的 MIME 类型
_IMAGE_FORMAT_TO_MIME: dict[str, str] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}

# 单张图片允许的最大像素数（防御解压缩炸弹）
MAX_IMAGE_PIXELS = 40_000_000

# 格式转换时 JPEG 的编码质量
_JPEG_QUALITY = 90


class ImageFormatError(ValueError):
    """图片无法识别、格式不受支持或尺寸超限，异常信息可直接展示给模型。"""


def _check_image_pixels(image: Image.Image, max_pixels: int) -> None:
    """校验图片像素规模，防御解压缩炸弹

    Args:
        image: 已打开的 Pillow 图片对象
        max_pixels: 允许的最大像素数
    """
    if image.width * image.height > max_pixels:
        raise ImageFormatError("图片尺寸过大")


def _convert_image(image: Image.Image) -> tuple[bytes, str]:
    """把模型不支持的图片格式转换为受支持的格式

    带透明通道的图片转换为 PNG 以保留透明度，其余统一转换为 JPEG。

    Args:
        image: 已打开的 Pillow 图片对象

    Returns:
        tuple[bytes, str]: (转换后的图片数据, MIME 类型)
    """
    buffer = io.BytesIO()
    if image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info):
        image.convert("RGBA").save(buffer, format="PNG")
        return buffer.getvalue(), "image/png"
    image.convert("RGB").save(buffer, format="JPEG", quality=_JPEG_QUALITY)
    return buffer.getvalue(), "image/jpeg"


def normalize_image(data: bytes, max_pixels: int = MAX_IMAGE_PIXELS) -> tuple[bytes, str]:
    """校验图片内容并归一化为模型支持的格式

    Args:
        data: 图片二进制数据
        max_pixels: 允许的最大像素数，测试或特殊场景可覆盖

    Returns:
        tuple[bytes, str]: (可安全送入模型的图片数据, 真实 MIME 类型)

    Raises:
        ImageFormatError: 内容为空、不是可识别的图片、格式无法转换或尺寸超限
    """
    if not data:
        raise ImageFormatError("图片内容为空")
    try:
        with Image.open(io.BytesIO(data)) as image:
            _check_image_pixels(image, max_pixels)
            mime_type = _IMAGE_FORMAT_TO_MIME.get((image.format or "").upper())
            if mime_type is not None:
                # 触发一次完整解码，提前发现截断/损坏的图片
                image.load()
                return data, mime_type
            return _convert_image(image)
    except ImageFormatError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as e:
        raise ImageFormatError("链接内容不是可识别的图片") from e


def image_data_url(data: bytes, mime_type: str) -> str:
    """构造 data URL

    Args:
        data: 图片二进制数据
        mime_type: 图片 MIME 类型

    Returns:
        str: ``data:<mime>;base64,...`` 形式的字符串
    """
    return f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"


def build_image_part(data: bytes) -> tuple[dict[str, Any], str]:
    """校验并转换图片，构造 OpenAI 兼容的 image_url 内容块

    Args:
        data: 图片二进制数据

    Returns:
        tuple[dict, str]: (image_url 内容块, 最终 MIME 类型)

    Raises:
        ImageFormatError: 图片无法送入模型时
    """
    normalized, mime_type = normalize_image(data)
    return {"type": "image_url", "image_url": {"url": image_data_url(normalized, mime_type)}}, mime_type


def try_build_image_part(data: bytes) -> Optional[dict[str, Any]]:
    """构造 image_url 内容块，图片不合法时返回 None 而不是抛异常

    Args:
        data: 图片二进制数据

    Returns:
        Optional[dict]: image_url 内容块；图片无法识别时返回 None
    """
    try:
        part, _ = build_image_part(data)
    except ImageFormatError:
        return None
    return part


def sanitize_content_images(content: Any) -> tuple[Any, int]:
    """校验并修复消息 content 中的内联图片块

    历史消息可能保存了模型不支持的图片，或声明了错误的 MIME 类型，导致后续每轮
    请求都被上游拒绝。这里按图片真实格式重新生成 image_url 块，无法处理的图片
    直接移除。远程 URL 无法离线校验，原样保留。

    Args:
        content: 消息 content，通常是 list

    Returns:
        tuple[Any, int]: (处理后的 content, 被移除的图片数量)
    """
    if not isinstance(content, list):
        return content, 0
    result: list[Any] = []
    removed = 0
    for part in content:
        if not (isinstance(part, dict) and part.get("type") == "image_url"):
            result.append(part)
            continue
        image_url = part.get("image_url")
        url = image_url.get("url") if isinstance(image_url, dict) else None
        if not isinstance(url, str) or not url.startswith("data:image/"):
            # 远程 URL 或非内联图片，无法离线校验，交由上游处理
            result.append(part)
            continue
        header, separator, payload = url.partition(",")
        if not separator or ";base64" not in header:
            result.append(part)
            continue
        try:
            normalized, mime_type = normalize_image(base64.b64decode(payload, validate=True))
        except ValueError:
            # base64 损坏或图片格式不受支持，移除该图片块
            removed += 1
            continue
        sanitized_part = dict(part)
        sanitized_image_url = dict(image_url)
        sanitized_image_url["url"] = image_data_url(normalized, mime_type)
        sanitized_part["image_url"] = sanitized_image_url
        result.append(sanitized_part)
    return result, removed


def sanitize_messages_images(messages: list[Any]) -> int:
    """就地修复消息列表中的图片块，返回被移除的图片数量

    Args:
        messages: OpenAI 格式的消息列表（元素为 dict）

    Returns:
        int: 被移除的、模型无法处理的图片数量
    """
    removed = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        sanitized, count = sanitize_content_images(content)
        removed += count
        if sanitized != content:
            message["content"] = sanitized
    return removed
