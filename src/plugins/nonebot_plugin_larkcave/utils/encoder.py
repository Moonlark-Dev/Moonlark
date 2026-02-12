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

import time
from ..models import ImageData
import zlib
from nonebot_plugin_orm import async_scoped_session
import io
import imagehash
from PIL import Image


def calculate_perceptual_hash(image_data: bytes) -> str:
    """
    计算图片的感知哈希值
    :param image_data: 图片的字节数据
    :return: 感知哈希的十六进制字符串
    """
    try:
        img = Image.open(io.BytesIO(image_data))
        # 使用 average hash 算法，哈希大小为 16x16 以提高精度
        hash_value = imagehash.average_hash(img, hash_size=16)
        return str(hash_value)
    except Exception:
        return ""


async def encode_text(text: str) -> str:
    return text.replace("[", "&#91;").replace("]", "&#93;")


async def encode_image(cave_id: int, name: str, data: bytes, session: async_scoped_session) -> str:
    image_id = time.time()
    # 计算感知哈希
    p_hash = calculate_perceptual_hash(data)
    # 将压缩后的图片数据存入数据库
    compressed_data = zlib.compress(data)
    session.add(ImageData(id=image_id, name=name, belong=cave_id, p_hash=p_hash, image_data=compressed_data))
    await session.commit()
    return f"[[Img:{image_id}]]]"
