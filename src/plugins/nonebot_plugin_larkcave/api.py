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
from fastapi import status, Response
import traceback

from fastapi import HTTPException
from nonebot.log import logger
from nonebot import get_app
from nonebot_plugin_orm import get_session, get_scoped_session
from sqlalchemy import select
from typing import AsyncGenerator

from .types import RandomCaveResponse, Image
from .utils.cave import get_cave
from nonebot_plugin_larkuser import get_user
from .models import ImageData, CaveData
from .utils.decoder import get_image
from .config import config

app = get_app()


async def get_image_data(cave_id: int) -> AsyncGenerator[Image, None]:
    """
    获取回声洞图片列表（生成器）
    :param cave_id: 所属回声洞 ID
    """
    session = get_scoped_session()
    for image in await session.scalars(select(ImageData).where(ImageData.belong == cave_id)):
        try:
            data = await get_image(image.id, session)
            yield Image(
                id=float(image.id),
                name=str(image.name),
                data=base64.b64encode(data.data).decode()
            )
        except Exception as e:
            logger.error(f"获取 CAVE 图片信息失败 ({image.id=}, {e=}): {traceback.format_exc()}")
    await session.close()


@app.get("/api/cave/random")
async def _() -> RandomCaveResponse:
    async with get_session() as session:
        cave = await get_cave(session)
        return {
            "id": int(cave.id),
            "content": str(cave.content),
            "time": cave.time.timestamp(),
            "author": (await get_user(cave.author)).get_nickname(),
            "images": [img async for img in get_image_data(cave.id)],
        }



async def get_images() -> AsyncGenerator[ImageData, None]:
    session = get_scoped_session()
    image_list = await session.scalars(select(ImageData.id))
    for image_id in image_list:
        image = await session.get_one(ImageData, {"id": image_id})
        belong = await session.get(CaveData, {"id": image.belong})
        if belong is not None and belong.public:
            yield image
    await session.close()



@app.get("/api/cave/images")
async def _() -> dict[str, str]:
    response = {}
    async for image in get_images():
        file_name = f"{image.id}.{image.name.split('.')[-1]}"
        response[file_name] = f"{config.moonlark_api_base}/api/cave/images/{file_name}"
    return response



@app.get("/api/cave/images/{file_name}")
async def _(file_name: str) -> Response:
    session = get_scoped_session()
    image_id = ".".join(file_name.split(".")[:-1])
    if (image_data := await session.get(ImageData, {"id": image_id})) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        image = await get_image(str(image_data.id), session)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await session.close()
    return Response(image.data)
