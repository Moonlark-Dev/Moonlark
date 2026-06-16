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
from typing import Optional

import httpx

from .client import client


async def generate_image(
    prompt: str,
    model: str = "gpt-image-1",
    size: str = "1024x1024",
    quality: str = "low",
) -> bytes:
    """调用 OpenAI 图像生成 API 生成图片

    Args:
        prompt: 图片描述文本
        model: 图像生成模型名称
        size: 图片尺寸，可选 "1024x1024", "1536x1024", "1024x1536", "auto"
        quality: 图片质量，可选 "low", "medium", "high"

    Returns:
        图片的二进制数据

    Raises:
        Exception: API 调用失败时抛出异常
    """
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
