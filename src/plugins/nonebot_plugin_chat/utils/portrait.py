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

from pathlib import Path
from typing import Optional

import aiofiles

# Moonlark 自己的画像，随插件内置，供 draw_image 作为参考图传给图像生成模型
PORTRAIT_PATH = Path(__file__).parent.parent / "resource" / "Moonlark.png"
PORTRAIT_MIME_TYPE = "image/png"
PORTRAIT_FILE_NAME = "Moonlark.png"

_portrait_cache: Optional[bytes] = None


async def get_moonlark_portrait() -> bytes:
    """读取内置的 Moonlark 画像

    图片内容在首次读取后缓存，后续调用直接复用，避免重复磁盘 IO。

    Returns:
        bytes: 画像的 PNG 二进制数据

    Raises:
        FileNotFoundError: 内置画像文件缺失
    """
    global _portrait_cache
    if _portrait_cache is None:
        async with aiofiles.open(PORTRAIT_PATH, mode="rb") as f:
            _portrait_cache = await f.read()
    return _portrait_cache
