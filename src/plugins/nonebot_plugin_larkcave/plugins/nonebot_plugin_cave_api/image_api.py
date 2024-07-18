from typing import AsyncGenerator
from fastapi.responses import Response
from nonebot import get_app
from nonebot_plugin_orm import get_scoped_session
from fastapi import status
from fastapi.exceptions import HTTPException
from sqlalchemy.exc import NoResultFound
from sqlalchemy import select

from .config import config
from ...models import ImageData, CaveData
from ...decoder import get_image
app = get_app()


async def get_images() -> AsyncGenerator[ImageData, None]:
    session = get_scoped_session()
    image_list = (await session.scalars(select(ImageData.id)))
    for image_id in image_list:
        image = await session.get_one(ImageData, {"id": image_id})
        belong = await session.get_one(CaveData, {"id": image.belong})
        if belong.public:
            yield image
    await session.close()


@app.get("/api/cave/images")
async def _() -> dict[str, str]:
    response = {}
    async for image in get_images():
        file_name = f"{image.id}.{image.name.split('.')[-1]}"
        response[file_name] = f"{config.cave_api_base_url}/api/cave/images/{file_name}"
    return response


@app.get("/api/cave/images/{file_name}")
async def _(file_name: str) -> Response:
    session = get_scoped_session()
    image_id = ".".join(file_name.split(".")[:-1])
    try:
        image_data = await session.get_one(ImageData, {"id": image_id})
    except NoResultFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        image = await get_image(image_data.id, session)
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await session.close()
    return Response(image.data)
