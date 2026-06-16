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

import base64
import re
from typing import Optional

import httpx

from .client import client
from .model_config import get_model_for_identify

VALID_SIZES = {"auto", "1024x1024", "1536x1024", "1024x1536", "256x256", "512x512", "1792x1024", "1024x1792"}
CUSTOM_SIZE_PATTERN = re.compile(r"^\d+x\d+$")


def validate_size(size: str) -> str:
    """校验图片尺寸参数

    Args:
        size: 图片尺寸字符串

    Returns:
        校验后的尺寸字符串

    Raises:
        ValueError: 尺寸格式不合法时抛出
    """
    if size in VALID_SIZES:
        return size
    if CUSTOM_SIZE_PATTERN.match(size):
        parts = size.split("x")
        width, height = int(parts[0]), int(parts[1])
        if width % 16 != 0 or height % 16 != 0:
            raise ValueError(f"尺寸 {size} 的宽高必须都是 16 的倍数")
        aspect = width / height
        if aspect < 1 / 3 or aspect > 3:
            raise ValueError(f"尺寸 {size} 的宽高比必须在 1:3 到 3:1 之间")
        if width > 3840 or height > 2160:
            raise ValueError(f"尺寸 {size} 超过最大支持分辨率 3840x2160")
        return size
    raise ValueError(f"不支持的图片尺寸: {size}")


async def generate_image(
    prompt: str,
    identify: str = "Draw Image",
    size: str = "auto",
    quality: str = "high",
) -> bytes:
    """调用 OpenAI 图像生成 API 生成图片

    Args:
        prompt: 图片描述文本
        identify: 用于识别模型配置的应用标识，可通过 /model 命令为该标识指定模型
        size: 图片尺寸，支持标准尺寸 (auto/1024x1024/1536x1024/1024x1536) 或自定义 WxH 格式（宽高需为 16 的倍数）
        quality: 图片质量，可选 "auto", "low", "medium", "high"

    Returns:
        图片的二进制数据

    Raises:
        ValueError: 尺寸参数不合法时抛出
        Exception: API 调用失败时抛出异常
    """
    size = validate_size(size)
    model = await get_model_for_identify(identify)
    response = await client.images.generate(
        model=model,
        prompt=prompt,
        size=size,
        quality=quality,
        n=1,
    )

    if not response.data or len(response.data) == 0:
        raise Exception("图像生成 API 返回了空数据")

    image_item = response.data[0]

    # 优先使用 b64_json（如果返回了 base64 编码的图片）
    if image_item.b64_json:
        return base64.b64decode(image_item.b64_json)

    # 如果返回了 URL，则下载图片
    if image_item.url:
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            img_response = await http_client.get(image_item.url)
            img_response.raise_for_status()
            return img_response.content

    raise Exception("图像生成 API 返回的数据中不包含图片")
