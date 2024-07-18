import base64
from nonebot import get_app
from nonebot_plugin_orm import get_session, get_scoped_session
from sqlalchemy import select
from typing import AsyncGenerator

from .types import RandomCaveResponse, Image
from ...__main__ import get_cave
from ....nonebot_plugin_larkuser import get_user
from ...models import ImageData
from ...decoder import get_image

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
        except Exception:
            continue
        yield {
            "id": float(image.id),
            "name": str(image.name),
            "data": base64.b64encode(data.data).decode(),
        }
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
            "images": [img async for img in get_image_data(cave.id)]
        }
