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
import uuid
from ..models import ImageData
import aiofiles
import zlib
from .decoder import data_dir
from nonebot_plugin_orm import async_scoped_session


async def encode_text(text: str) -> str:
    return text.replace("[", "&#91;").replace("]", "&#93;")


async def encode_image(cave_id: int, name: str, data: bytes, session: async_scoped_session) -> str:
    image_id = time.time()
    file_id = uuid.uuid4().hex
    session.add(ImageData(id=image_id, file_id=file_id, name=name, belong=cave_id))
    async with aiofiles.open(data_dir.joinpath(file_id), "wb") as f:
        await f.write(zlib.compress(data))
    await session.commit()
    return f"[[Img:{image_id}]]]"
