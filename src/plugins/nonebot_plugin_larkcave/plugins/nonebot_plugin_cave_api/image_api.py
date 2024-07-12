from typing import AsyncGenerator
from fastapi.responses import Response
from nonebot import get_app
from nonebot_plugin_orm import get_session
from ...models import ImageData, CaveData
from fastapi.exceptions import HTTPException
from sqlalchemy.exc import NoResultFound
from sqlalchemy import select
from .config import config

app = get_app()


async def get_images() -> AsyncGenerator[ImageData, None]:
    session = get_session()
    image_list = (await session.scalars(select(ImageData.id))).all()
    for image_id in image_list:
        image = await session.get_one(ImageData, {"id": image_id})
        belong = await session.get_one(CaveData, {"id": image.belong})
        if belong.public:
            yield image


@app.get("/api/cave/images")
async def _() -> dict[str, str]:
    response = {}
    async for image in get_images():
        file_name = f"{image.id}.{image.name.split('.')[-1]}"
        response[file_name] = f"{config.cave_api_base_url}/api/cave/images/{file_name}"
    return response


@app.get("/api/cave/images/{file_name}")
async def _(file_name: str) -> Response:
    session = get_session()
    try:
        image = await session.get_one(ImageData, {"id": ".".join(file_name.split(".")[:-1])})
    except NoResultFound:
        raise HTTPException(404)
    return Response(image.data)
